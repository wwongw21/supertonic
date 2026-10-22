# supertonic engineering handoff

Review date: **22 October 2026**. All findings remain **OPEN**. This handoff contains proposed repairs and release checks; no runtime source fixes or repaired-behavior acceptance are claimed.

**Reviewed source:** [`main` at `7e2804f96016a7028cb1ed627353c61c1e9dd281`](https://github.com/wwongw21/supertonic/tree/7e2804f96016a7028cb1ed627353c61c1e9dd281).

The full structured handoff is in [report.json](report.json). The historical commands and results below retain their original `/workspace` paths and are not portable reruns. Use the checked-in [standard-library reproducer](diagnostics/repro_pinned_sources.py) from the repository root; its fresh output is [captured here](evidence/portable-probe-2026-10-22.txt). It demonstrates pre-fix behavior only and does not apply runtime repairs.

## Audience and required outcome

### Audience

1. Maintainer implementing corrections

2. Reviewer checking behavior, preservation of user data and release readiness

### Outcome

null

## Scope and reviewed branches

Python and Node/browser ONNX helpers and example entry points, C++ helper/build configuration, Rust CLI and helper review, language-package manifests, top-level cross-language test script; remaining mobile/native language implementations sampled. No AGENTS.md present.

## Architecture

### Runtime flow

Each language example loads external model assets from assets/onnx and preset style JSONs, normalizes text, predicts duration, encodes text, generates denoising latents and vocodes audio. Long-form helpers split text and concatenate chunk waveforms; CLI/UI code then exports WAV using the reported duration.

### Components

#### Item 1

##### Component

Python reference example

##### Files

1. py/helper.py

2. py/example_onnx.py

3. py/requirements.txt

4. py/uv.lock

##### Role

ONNX inference orchestration, text processing and chunking, long-form concatenation, batch entry point and WAV export.

#### Item 2

##### Component

Node.js and browser examples

##### Files

1. nodejs/helper.js

2. nodejs/example_onnx.js

3. web/helper.js

4. web/main.js

5. nodejs/package.json

6. web/package.json

##### Role

Equivalent local/browser runtime helpers and export/UI; source shows the same full-waveform concatenation versus summed-duration pattern.

#### Item 3

##### Component

Native/mobile examples

##### Files

1. cpp/helper.cpp

2. cpp/CMakeLists.txt

3. rust/src/helper.rs

4. rust/src/example_onnx.rs

5. java/Helper.java

6. csharp/Helper.cs

7. go/helper.go

8. swift/Sources/Helper.swift

9. flutter/lib/helper.dart

10. ios/ExampleiOSApp/TTSService.swift

##### Role

Separate platform ports with their own dependency/runtime and lifetime details. Source sampling is not a full build or parity certification.

#### Item 4

##### Component

Cross-language smoke runner

##### Files

1. test_all.sh

2. README.md

##### Role

Interactive inference script and model/toolchain instructions. The script needs external model assets and multiple native runtimes; it was not run.

### Contracts to preserve

1. Existing language-specific CLI flags, model/style input formats and CPU default.

2. Single-speaker output and batch row ordering; a single flattened batch array must not mix speaker samples.

3. Silence is inserted between chunks only, at the requested sample count.

4. Reported duration must agree with actual exported sample count within rounding tolerance.

5. The examples repository is independent of the supertonic-py package; SDK test counts are not evidence of example correctness.

## Implementation sequence

### Item 1

#### Order

1

#### Findings

1. STON-1

#### Depends on

None recorded.

#### Deliverable

Model-free padded-waveform regression; per-chunk trimming and sample-derived output duration in Python. Preserve batch behavior.

### Item 2

#### Order

2

#### Findings

1. STON-2

#### Depends on

None recorded.

#### Deliverable

Bounded chunking regressions and a fallback split policy for long sentences/words and Japanese text.

### Item 3

#### Order

3

#### Findings

1. STON-1

#### Depends on

1. 1

#### Deliverable

Audit Node/browser and native ports against the accepted sample-count contract; apply equivalent corrections only where the defect is confirmed.

### Item 4

#### Order

4

#### Findings

1. STON-1

2. STON-2

#### Depends on

1. 1

2. 2

3. 3

#### Deliverable

Real model long-form audio acceptance and per-runtime build/run checks. All remain NOT RUN.

## Findings and implementation handoff

### STON-1 Medium: Long-form output trims off the end after concatenating padded chunks

**Status:** OPEN. [Pinned source](https://github.com/wwongw21/supertonic/blob/7e2804f96016a7028cb1ed627353c61c1e9dd281/py/helper.py#L234).

#### Evidence classification

Confirmed through the validation described below

#### Observed mechanism

TextToSpeech.__call__ concatenates full vocoder waveforms while adding only predicted durations. sample_noisy_latent rounds each latent length up to a chunk boundary (helper.py:165-169), and _infer returns wav unchanged. example_onnx.py:113 then trims the concatenated waveform to the sum of predicted durations. Internal padding remains in the middle, so the final trim removes audio from later chunks. Node and browser helpers have the same concatenate/sum-duration structure (nodejs/helper.js:289-299; web/helper.js:287-297).

#### Impact and scope

Multi-chunk long-form exports contain extra gaps at chunk boundaries and lose the final portion of the synthesized passage as accumulated padding grows. Single-chunk output is unaffected by this particular bug.

#### Repair direction

Trim each individual waveform to its actual/predicted sample count before concatenating; compute the combined duration from the final concatenated sample count. Preserve independently trimmed rows for batched outputs.

#### Verification already obtained

Confirmed orchestration using the real Python helper with _infer replaced by deterministic padded outputs: two chunks [1,1,1,0,0] and [2,2,2,0,0], each with duration 0.3 s at 10 Hz, export as [1,1,1,0,0,2], losing the last two nonzero samples. No real ONNX model was run; the test proves padding/concatenation/trim behavior.

#### Locations

##### Item 1

###### File

py/helper.py

###### Lines

1. 234

2. 243

###### Url

<https://github.com/wwongw21/supertonic/blob/7e2804f96016a7028cb1ed627353c61c1e9dd281/py/helper.py#L234>

#### Change surface

1. py/helper.py: TextToSpeech.__call__, _infer sample/duration contract

2. py/example_onnx.py: final export trim

3. nodejs/helper.js: call and nodejs/example_onnx.js export parity

4. web/helper.js: call and export parity

5. Native/mobile helpers only after source-specific confirmation

#### Repair steps

1. Add the recorded two-padded-chunk fixture as a regression using the real helper and deterministic _infer outputs. Include explicit nonzero markers in the final chunk so truncation is observable without playback.

2. Before concatenation, trim each waveform row to its own predicted/accepted sample count, clamped to actual available samples and using one explicit rounding rule.

3. Insert exactly the requested silence sample count between chunks. Sum actual sample counts after trimming/concatenation and derive the returned duration from that total.

4. Keep the batch path independently aware of each row's duration and padded row stride; do not flatten multiple speakers into one untrimmed long-form stream.

5. Check exporters for a redundant final trim and ensure it cannot remove another chunk's real samples because of floating-point rounding.

6. Port the accepted sample-count contract to Node/browser helpers that show the same pattern, and audit each native port independently. Add runtime-specific tests rather than claiming Python fixtures validate all ports.

#### Invariants

1. Every intended non-padding sample from every chunk is emitted in order.

2. No vocoder padding is retained between chunks as unintended silence.

3. A final export trim does not cut later audio to compensate for earlier padding.

4. Returned duration matches the output sample count divided by sample_rate within one sample.

5. Batch row/speaker ordering and single-chunk output remain correct.

#### Acceptance criteria

1. Recorded fake chunks export as [1,1,1,2,2,2] at zero added silence, not [1,1,1,0,0,2].

2. With nonzero silence, output contains exactly the configured zero samples between complete chunks.

3. Different padding amounts across 3+ chunks do not change the final nonzero ending.

4. Duration/sample count agrees for odd sample counts and fractional predicted durations.

5. Real long-form speech retains the final word and expected pauses; this acoustic check remains NOT RUN.

#### Regression scenarios

1. One chunk without padding

2. One chunk with padding

3. Two and many chunks with different pad lengths

4. Zero and nonzero configured silence

5. Sample-rate rounding and fractional durations

6. Predicted length exceeds available waveform; clamp or explicit error policy

7. Batch rows of unequal duration

8. English, Japanese/Korean chunk sizes and empty text behavior

#### Risks

1. Trimming on predicted duration may expose off-by-one errors; use a single sample-count rule and clamp explicitly.

2. Duration predictions can differ from acoustically useful waveform tails; real speech listening must validate the chosen trim policy.

3. More than one platform repeats this algorithm; a Python-only repair does not establish native/browser parity.

#### Rollback

Retain pre-change generated output for comparison and revert only the concatenation/export correction if it corrupts sample ordering. Until repaired, synthesize/trim separate chunks outside the helper. No persisted schema migration is required.

#### Repair validation status

NOT RUN — no source edits, fixed-code tests or real audio acceptance.

### STON-2 Medium: The Python example does not enforce its maximum chunk length

**Status:** OPEN. [Pinned source](https://github.com/wwongw21/supertonic/blob/7e2804f96016a7028cb1ed627353c61c1e9dd281/py/helper.py#L418).

#### Evidence classification

Confirmed through the validation described below

#### Observed mechanism

An overlong sentence is assigned unchanged to current_chunk; there is no word/character fallback. ASCII-only sentence boundary detection also misses Japanese punctuation.

#### Impact and scope

Unpunctuated long passages and Japanese paragraphs bypass the intended 300/120-character inference limits, undermining the long-form chunking contract. No claim of measured runtime cost is made.

#### Repair direction

Split overlong sentences at words then at bounded character positions when no whitespace is available; cover Japanese sentence punctuation. Apply the same behavior to the SDK helper.

#### Verification already obtained

Real helper.chunk_text('word '*400,max_len=300) returns [1999] as the chunk length; reproduced without loading any model.

#### Locations

##### Item 1

###### File

py/helper.py

###### Lines

1. 418

2. 427

###### Url

<https://github.com/wwongw21/supertonic/blob/7e2804f96016a7028cb1ed627353c61c1e9dd281/py/helper.py#L418>

#### Change surface

1. py/helper.py: chunk_text

2. py/helper.py: TextToSpeech.__call__

3. Model-free Python helper regression harness under a test location chosen by the maintainer

4. Other language helper chunkers only after auditing their own behavior

#### Repair steps

1. Define maximum length over Python Unicode characters and preserve the existing paragraph/sentence ordering and abbreviation rules.

2. For a sentence longer than max_len, split at available whitespace boundaries; if an individual span still exceeds the limit, split it by bounded character positions.

3. Recognize common Unicode sentence punctuation so Japanese text can retain useful boundaries; hard fallback must still enforce the maximum when punctuation/whitespace is absent.

4. Return nonempty bounded chunks without dropping, reordering or duplicating input text. Preserve the documented whitespace-normalization behavior.

5. Add regressions for unpunctuated words, one long word, Japanese text without spaces, Korean text, abbreviations and exact limits. Coordinate behavior with the sibling Python implementation without introducing a cross-repository runtime dependency.

#### Invariants

1. Every returned chunk is nonempty and has len(chunk) <= configured max_len.

2. Original meaningful characters retain order and are emitted exactly once.

3. Empty/whitespace input and existing sentence/paragraph behavior remain defined.

4. Minimum-limit validation remains consistent with the public SDK or example contract.

#### Acceptance criteria

1. chunk_text('word '*400,max_len=300) returns multiple chunks, all <=300, instead of [1999].

2. A Japanese passage longer than 120 characters with no ASCII whitespace yields bounded chunks while preserving all characters.

3. One token longer than the limit is split safely and recombines to the original token.

4. Existing abbreviation and paragraph tests remain green.

#### Regression scenarios

1. Input length max_len-1/max_len/max_len+1

2. One very long word and one long sentence

3. Japanese 。！？ punctuation without following spaces

4. Korean decomposed/combined characters

5. Emoji, combining marks and expression-tag text

6. Empty input, repeated whitespace, paragraphs and common abbreviations

#### Risks

1. A strict character fallback may split a grapheme cluster or expression tag, affecting synthesis quality. Prefer safe text boundaries while maintaining a real length bound; define behavior for indivisible tokens explicitly.

2. More chunks add pauses and inference overhead. Exact memory/latency improvements and audio quality have not been measured.

#### Rollback

Revert the chunker change if it drops text or materially degrades speech; clients can pre-split bounded passages temporarily. No data format migration is required.

#### Repair validation status

NOT RUN — only the current oversized result was observed; no repair or fixed regression suite has run.

## Review date

2026-10-22

## Owner

wwongw21

## Handoff status

All findings OPEN; runtime repairs and acceptance checks are still PROPOSED. Only the portable diagnostic and handoff evidence were added.

## Evidence boundary

Source at the pinned commit, recorded lightweight tests and focused bug reproductions. Fake inference does not establish real synthesis quality or native runtime compatibility.

## Authorization boundary

This handoff describes proposed changes only. Source repositories and remote services were not modified.

## Evidence artifacts

1. /workspace/review/supertonic.json

2. /workspace/review/repro_supertonic.py

## Environment

### Execution

Linux managed cloud environment

### Recorded dependency versions

#### Python

3.12.14

#### Numpy

2.3.5

#### Pytest

9.1.1

#### Onnxruntime

1.31.0

#### Soundfile

0.14.0

#### Huggingface hub

2.2.0

#### Fastapi

0.141.1

#### Pydantic

2.13.4

#### Python multipart

0.0.32

#### Httpx

0.28.1

### Versions note

Versions read from the isolated verification environment; no project dependency manifest or lock file changed.

## Setup

### Working directory

/workspace

### Commands

1. ```
   python -m venv --system-site-packages /workspace/review/supertonic-venv
   ```

2. ```
   /workspace/review/supertonic-venv/bin/pip install pytest onnxruntime soundfile huggingface-hub python-multipart -q
   ```

### Status

RAN during original review; do not rerun to claim additional coverage.

### Model requirement

The focused reproducer needs both local repositories at their pinned commits but downloads no model. The offline SDK unit selection also downloads no model.

## Branch

main

## Source directory

/workspace/repos/supertonic

## Desired outcome

Preserve the complete ending and intended pauses of multi-chunk audio exports, and enforce the Python example's configured text chunk limit without losing or reordering text.

## Coverage

Python and Node/browser ONNX helpers and example entry points, C++ helper/build configuration, Rust CLI and helper review, language-package manifests, top-level cross-language test script; remaining mobile/native language implementations sampled. No AGENTS.md present.

## Current mitigations and limits

### Item 1

#### Mitigation

Synthesize bounded chunks separately, trim each generated chunk to its own duration and concatenate the trimmed audio with the desired pauses in the caller.

#### Addresses

1. STON-1

#### Limit

Simply increasing the final reported duration preserves the ending but retains padding gaps; it does not repair timing consistently.

### Item 2

#### Mitigation

Pre-split text into passages shorter than the configured language limit, including Japanese paragraphs without spaces.

#### Addresses

1. STON-2

#### Limit

Caller workaround only. Preserve punctuation/expression tags and validate the final joined speech manually.

## Tests and reproductions

### Item 1

#### Name

Combined bug demonstrator, examples section

#### Working directory

/workspace

#### Command

```
HF_HUB_OFFLINE=1 /workspace/review/supertonic-venv/bin/python /workspace/review/repro_supertonic.py
```

#### Prerequisites

Both local repositories at pinned paths; isolated Python environment with numpy and onnxruntime. The combined script also imports SDK FastAPI/soundfile dependencies. No model weights needed.

#### Actual result

EXIT 0. Real helper with fake inference returns [[1,1,1,0,0,2,2,2,0,0]]; existing final-duration export produces [1,1,1,0,0,2], losing two nonzero ending samples. Example chunker prints [1999] for max_len=300.

#### Proves

An asserted padding/concatenation/export control-flow failure and a measured chunk-length contract failure.

#### Does not prove

Real model acoustic quality, actual vocoder output padding distribution, native runtime correctness or browser/mobile behavior.

#### After repair

The original truncation assertion encodes the bug and should fail after a correct repair. Replace it with exact complete-sample expectations and sample/duration consistency.

## Test attribution

No standalone supertonic examples test suite was run. The 86 passing SDK/server tests belong exclusively to supertonic-py, not this repository.

## Remaining acceptance not run

### Item 1

#### Status

NOT RUN

#### Scenario

Python model-free regression suite for padding, durations and text preservation after repair.

#### Prerequisites

Fixed code and new tests; no weights required.

### Item 2

#### Status

NOT RUN

#### Scenario

Real Python ONNX single-chunk, multi-chunk and batch synthesis using downloaded Supertone/supertonic-3 assets. Check final word, pause lengths and sample count.

#### Suggested command

```
From /workspace/repos/supertonic/py: uv run example_onnx.py --n-test 1 --lang en --text "A bounded first sentence. A bounded second sentence." --save-dir /workspace/review/supertonic-real-output
```

#### Prerequisites

uv/Python, declared dependencies, real ONNX and voice files in ../assets. To exercise chunk boundaries, use a controlled passage longer than 300 characters or explicit paragraphs.

### Item 3

#### Status

NOT RUN

#### Scenario

Node.js and browser real model smoke and playback checks after mirrored padding repair.

#### Suggested commands

1. ```
   From nodejs: npm install && npm start
   ```

2. ```
   From web: npm install && npm run build; then run dev/preview and inspect actual synthesis in a browser.
   ```

#### Prerequisites

Node/npm, declared ONNX runtime packages and configured model assets. Commands are examples for future acceptance, not prior results.

### Item 4

#### Status

NOT RUN

#### Scenario

Build and execute C++, Rust, Go, Java, C#, Swift, iOS and Flutter implementations for single/batch/long-form parity.

#### Prerequisites

Platform-specific native runtimes and model assets; iOS/macOS/mobile checks require appropriate SDKs/devices.

### Item 5

#### Status

NOT RUN

#### Scenario

Interactive cross-language inference runner.

#### Suggested command

```
From /workspace/repos/supertonic: bash test_all.sh; select mode 4 and decline deletion of results unless working in a disposable copy.
```

#### Prerequisites

All toolchains/model assets and enough time/storage. Inspect its prompted cleanup behavior before selecting an option.

## Operational notes

1. The upstream archive/support notice in README.md means this fork should decide who owns compatibility fixes and model-asset availability; no external support availability was verified.

2. All native/mobile/browser acceptance is explicitly unexecuted.

3. Root recorded no Actions runs on this fork; absence of runs does not establish pass/fail.

## All findings open

true

## Implementation performed

false

## Delivery and diagnostic files

### Destination repository

wwongw21/supertonic

### Status

All findings remain OPEN; documentation transfer only.

### Portable evidence

The historical `/workspace` commands and outputs remain unchanged as records of the original review. The new portable run is separate; it records its UTC time, Python/OS, source pin, and LF-normalized SHA-256 hashes for every source file it executes.

### Diagnostics included

Run from the repository root with Python 3.9 or later:

```text
python docs/reviews/2026-10-22/diagnostics/repro_pinned_sources.py
```

The probe uses only the Python standard library. It AST-extracts the pinned `TextToSpeech.__call__`, `chunk_text`, and example waveform-trim assignment. It supplies deterministic fake inference outputs and a tiny array shim. No project dependencies, ONNX Runtime, model weights, or model initialization are used. The source hash checks normalize CRLF to LF, so they work from Windows and LF checkouts.

The captured run reproduced both pre-fix results: two padded fake chunk outputs were trimmed by the example's duration-based slice to `[1, 1, 1, 0, 0, 2]`, losing the last two nonzero samples; and `chunk_text("word " * 400, max_len=300)` returned a 1,999-character chunk.

The evidence is [portable-probe-2026-10-22.txt](evidence/portable-probe-2026-10-22.txt). It is a new source-level reproduction and does not replace the historical run results above.

### Not included

Original environments, model weights, user data and complete source snapshots are not included. Clone the pinned source and follow the recorded prerequisites. Bug-demonstration scripts intentionally assert pre-fix behavior; they are not a post-fix passing suite.

### Combined probe

The historical `repro_supertonic.py` still is not included. This repository now contains a self-contained probe for its two recorded Python example observations; the sibling `supertonic-py` repository has a separate probe for its four SDK observations. Each run checks its own pinned source hashes.


## Remaining review limits

1. No real model inference, synthesis quality evaluation, GPU execution, browser UI, mobile app, full native-language builds or packaged release testing.

2. Tests use deterministic fake inference outputs and temporary user-style directories where appropriate; these reproduce control-flow/contracts rather than audio quality.

3. No GitHub Actions runs exist on these forks according to root's connector query; this is absent evidence, not a failing CI result.

4. Runtime source files were not edited; the historical test imports may generate ignored __pycache__ files.

