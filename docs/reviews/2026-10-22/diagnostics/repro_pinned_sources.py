#!/usr/bin/env python3
"""Reproduce the reviewed pre-fix Python example paths using only stdlib.

Run from any working directory with Python 3.9 or later. The script locates
the repository from its own path, checks LF-normalized source hashes against
the recorded source pin, and executes AST-extracted helper code with fake
inference outputs and a tiny array shim. It intentionally demonstrates the
old behavior; it does not load ONNX Runtime or model weights.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[4]
SOURCE_PIN = "7e2804f96016a7028cb1ed627353c61c1e9dd281"
SOURCE_HASHES = {
    "py/helper.py": "b14b1da8a018aa4db6ca8cbb927c32590bfc889b49116ea344c56e8351d94279",
    "py/example_onnx.py": "2ef5371dc02b9425b130ecc480abeb4714781fabe2059e4f9c68dd5e546dec49",
}


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def check_source_hashes() -> None:
    print(f"repository=supertonic; source_pin={SOURCE_PIN}")
    print("hash_method=SHA-256 of UTF-8 source bytes after CRLF-to-LF normalization")
    for relative_path, expected in SOURCE_HASHES.items():
        raw = (ROOT / relative_path).read_bytes().replace(b"\r\n", b"\n")
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"source mismatch for {relative_path}: expected {expected}, got {actual}"
            )
        print(f"source_sha256={actual}  path={relative_path}")


def parse_source(relative_path: str) -> ast.Module:
    return ast.parse(read_source(relative_path), filename=relative_path)


def find_function(tree: ast.AST, name: str, class_name: str | None = None):
    if class_name is None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
    else:
        class_node = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
    raise LookupError(f"could not find {name} in source AST")


def clean_function(node):
    node = copy.deepcopy(node)
    node.decorator_list = []
    node.returns = None
    args = node.args
    for arg in args.posonlyargs + args.args + args.kwonlyargs:
        arg.annotation = None
    if args.vararg:
        args.vararg.annotation = None
    if args.kwarg:
        args.kwarg.annotation = None
    args.defaults = [ast.Constant(value=None) for _ in args.defaults]
    args.kw_defaults = [None if value is None else ast.Constant(value=None) for value in args.kw_defaults]
    return ast.fix_missing_locations(node)


def compile_helper(function_node, namespace: dict):
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            clean_function(function_node),
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    exec(compile(module, "<pinned-source-helper>", "exec"), namespace)
    return namespace[function_node.name]


class TinyVector:
    def __init__(self, values):
        self.values = list(values)

    def __getitem__(self, index):
        return TinyVector([self.values[index]])

    def item(self):
        return self.values[0]

    def tolist(self):
        return list(self.values)


class TinyDuration(TinyVector):
    def __add__(self, other):
        if isinstance(other, TinyDuration):
            return TinyDuration([left + right for left, right in zip(self.values, other.values)])
        return TinyDuration([value + other for value in self.values])

    def __iadd__(self, other):
        result = self + other
        self.values = result.values
        return self


class TinyWave:
    def __init__(self, rows):
        self.rows = [list(row) for row in rows]

    def __getitem__(self, index):
        row, samples = index
        return TinyVector(self.rows[row][samples])


class TinyNumpy:
    float32 = "float32"

    @staticmethod
    def zeros(shape, dtype=None):
        batch, samples = shape
        return TinyWave([[0] * samples for _ in range(batch)])

    @staticmethod
    def concatenate(arrays, axis=0):
        if axis != 1:
            raise ValueError("the probe only supports the source's axis=1 concatenation")
        batch = len(arrays[0].rows)
        return TinyWave(
            [
                [value for array in arrays for value in array.rows[row]]
                for row in range(batch)
            ]
        )


def probe_padded_waveform_trim() -> None:
    helper_tree = parse_source("py/helper.py")
    chunk_node = find_function(helper_tree, "chunk_text")
    call_node = find_function(helper_tree, "__call__", "TextToSpeech")
    namespace = {"re": re, "np": TinyNumpy}
    chunk_text = compile_helper(chunk_node, namespace)
    tts_call = compile_helper(call_node, namespace)

    text = "a" * 150 + ". " + "b" * 150 + "."
    chunks = chunk_text(text, max_len=300)
    assert [len(chunk) for chunk in chunks] == [151, 151]

    class FakeTTS:
        sample_rate = 10

    model = FakeTTS()
    inferred = 0

    def fake_infer(text_list, lang_list, style, total_step, speed):
        nonlocal inferred
        inferred += 1
        values = [1, 1, 1, 0, 0] if inferred == 1 else [2, 2, 2, 0, 0]
        return TinyWave([values]), TinyDuration([0.3])

    model._infer = fake_infer
    waveform, duration = tts_call(
        model,
        text=text,
        lang="en",
        style=SimpleNamespace(ttl=SimpleNamespace(shape=(1, 1))),
        total_step=1,
        silence_duration=0.0,
    )
    assert inferred == 2

    example_tree = parse_source("py/example_onnx.py")
    trim_assignment = None
    for node in ast.walk(example_tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "w" for target in node.targets):
            continue
        source = ast.unparse(node.value)
        if "text_to_speech.sample_rate" in source and "duration[b].item()" in source:
            trim_assignment = copy.deepcopy(node)
            break
    if trim_assignment is None:
        raise LookupError("the example's duration-based waveform trim was not found")

    trim_module = ast.Module(body=[ast.fix_missing_locations(trim_assignment)], type_ignores=[])
    ast.fix_missing_locations(trim_module)
    trim_namespace = {
        "wav": waveform,
        "b": 0,
        "text_to_speech": model,
        "duration": duration,
    }
    exec(compile(trim_module, "<pinned-example-trim>", "exec"), trim_namespace)
    exported = trim_namespace["w"].tolist()
    assert exported == [1, 1, 1, 0, 0, 2]

    print(
        "STON-1 padded chunks: actual helper chunks=2; fake inference rows="
        "[1,1,1,0,0] and [2,2,2,0,0]; durations=[0.3,0.3] at 10 Hz; "
        f"exact example trim exports={exported}"
    )


def probe_oversized_chunk() -> None:
    helper_tree = parse_source("py/helper.py")
    function = find_function(helper_tree, "chunk_text")
    chunk_text = compile_helper(function, {"re": re})
    lengths = [len(chunk) for chunk in chunk_text("word " * 400, max_len=300)]
    assert lengths == [1999]
    print(f"STON-2 chunk length: configured max=300; actual chunk lengths={lengths}")


def main() -> None:
    print(
        "Portable pre-fix reproduction; stdlib AST extraction runs the pinned "
        "TextToSpeech.__call__, chunk_text, and example trim assignment."
    )
    print("invocation=python docs/reviews/2026-10-22/diagnostics/repro_pinned_sources.py")
    print(f"run_utc={datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"python={platform.python_version()}; platform={platform.system()} {platform.release()}")
    print("mocks=fake _infer outputs and tiny NumPy-compatible array operations; no model files loaded")
    check_source_hashes()
    probe_padded_waveform_trim()
    probe_oversized_chunk()
    print("result=both historical source-level bug behaviors reproduced; no runtime fix applied")


if __name__ == "__main__":
    main()
