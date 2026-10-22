"""Offline regressions for sample accounting and bounded text chunks."""

import sys
import types
import unittest

import numpy as np

# The real helper only needs ONNX Runtime when a model is loaded. Keep this
# import-time type stub so these tests exercise the helper without model files.
try:
    import onnxruntime  # noqa: F401
except ImportError:
    onnxruntime = types.ModuleType("onnxruntime")
    onnxruntime.InferenceSession = object
    onnxruntime.SessionOptions = object
    sys.modules["onnxruntime"] = onnxruntime

from helper import Style, TextToSpeech, chunk_text


class FakeTextToSpeech(TextToSpeech):
    def __init__(self, responses, sample_rate=10):
        self.responses = list(responses)
        self.sample_rate = sample_rate
        self.inferred_texts = []

    def _infer(self, text_list, lang_list, style, total_step, speed):
        self.inferred_texts.append(list(text_list))
        wav, durations = self.responses.pop(0)
        return np.asarray(wav, dtype=np.float32), np.asarray(durations, dtype=np.float32)


def style():
    return Style(np.zeros((1, 1), dtype=np.float32), np.zeros((1, 1), dtype=np.float32))


class LongFormSampleTests(unittest.TestCase):
    def test_each_padded_chunk_is_trimmed_before_concatenation(self):
        tts = FakeTextToSpeech(
            [
                ([[1, 1, 1, 0, 0]], [0.3]),
                ([[2, 2, 2, 0, 0]], [0.3]),
            ]
        )

        wav, duration = tts("A sentence. " * 40, "en", style(), 1, speed=1.0, silence_duration=0)

        np.testing.assert_array_equal(wav, [[1, 1, 1, 2, 2, 2]])
        self.assertEqual(wav.shape, (1, 6))
        self.assertAlmostEqual(float(duration[0]), 0.6, places=6)
        self.assertEqual(len(tts.inferred_texts), 2)

    def test_multiple_chunks_keep_final_samples_and_exact_silence_count(self):
        tts = FakeTextToSpeech(
            [
                ([[1, 1, 1, 0, 0, 0]], [0.3]),
                ([[2, 2, 2, 0, 0]], [0.3]),
                ([[3, 3, 3, 0]], [0.35]),
                ([[4, 4, 4, 4, 0, 0]], [0.4]),
            ]
        )

        wav, duration = tts("x. " * 400, "en", style(), 1, speed=1.0, silence_duration=0.15)

        np.testing.assert_array_equal(
            wav,
            [[1, 1, 1, 0, 2, 2, 2, 0, 3, 3, 3, 0, 4, 4, 4, 4]],
        )
        self.assertEqual(wav.shape[1], 16)
        self.assertAlmostEqual(float(duration[0]), 1.6, places=6)

    def test_prediction_longer_than_available_waveform_is_clamped(self):
        tts = FakeTextToSpeech([([[7, 8, 9]], [0.8])])

        wav, duration = tts("A short sentence.", "en", style(), 1, speed=1.0, silence_duration=0)

        np.testing.assert_array_equal(wav, [[7, 8, 9]])
        self.assertAlmostEqual(float(duration[0]), 0.3, places=6)

    def test_empty_text_has_empty_waveform_and_zero_duration(self):
        tts = FakeTextToSpeech([])

        wav, duration = tts(" \n\t ", "en", style(), 1)

        self.assertEqual(wav.shape, (1, 0))
        self.assertEqual(duration.tolist(), [0.0])
        self.assertEqual(tts.inferred_texts, [])

    def test_negative_silence_is_rejected(self):
        tts = FakeTextToSpeech([([[1, 2, 0]], [0.2])])

        with self.assertRaises(ValueError):
            tts("A short sentence.", "en", style(), 1, silence_duration=-0.1)

    def test_batch_rows_keep_their_identity(self):
        rows = np.asarray([[11, 12, 0, 0], [21, 22, 23, 0]], dtype=np.float32)
        durations = np.asarray([0.2, 0.3], dtype=np.float32)
        tts = FakeTextToSpeech([(rows, durations)])

        batch_style = Style(
            np.zeros((2, 1), dtype=np.float32), np.zeros((2, 1), dtype=np.float32)
        )
        wav, actual_durations = tts.batch(
            ["one", "two"], ["en", "en"], batch_style, 1
        )

        np.testing.assert_array_equal(wav, rows)
        np.testing.assert_array_equal(actual_durations, durations)


class TextChunkingTests(unittest.TestCase):
    def assert_bounded_and_preserved(self, text, max_len):
        chunks = chunk_text(text, max_len=max_len)
        self.assertTrue(all(chunk for chunk in chunks))
        self.assertTrue(all(len(chunk) <= max_len for chunk in chunks))
        self.assertEqual(
            "".join("".join(chunk.split()) for chunk in chunks),
            "".join(text.split()),
        )
        return chunks

    def test_length_edges_and_one_long_token(self):
        for length in (9, 10):
            with self.subTest(length=length):
                self.assertEqual(chunk_text("x" * length, max_len=10), ["x" * length])
        chunks = self.assert_bounded_and_preserved("x" * 11, 10)
        self.assertEqual(chunks, ["x" * 10, "x"])
        self.assert_bounded_and_preserved("word " * 400, 300)

    def test_japanese_punctuation_without_spaces_stays_bounded(self):
        text = "これは最初の文です。これは二番目の文です！次の文です？" * 12
        chunks = self.assert_bounded_and_preserved(text, 120)
        self.assertGreater(len(chunks), 1)

    def test_korean_combining_sequences_and_expression_tags_are_preserved(self):
        text = (
            ("가" * 31)
            + ("\u1100\u1161" * 31)
            + ("\U0001f3f4\U000e0067\U000e0062\U000e007f" * 8)
            + ("😀" * 15)
        )
        self.assert_bounded_and_preserved(text, 32)

    def test_abbreviations_paragraphs_and_whitespace_behavior(self):
        self.assertEqual(
            chunk_text("Dr. Smith arrived. Next sentence.", max_len=100),
            ["Dr. Smith arrived. Next sentence."],
        )
        self.assertEqual(
            chunk_text("First paragraph.\n\nSecond paragraph.", max_len=100),
            ["First paragraph.", "Second paragraph."],
        )
        self.assertEqual(chunk_text("  repeated   spaces  ", max_len=100), ["repeated   spaces"])

    def test_empty_and_invalid_limits(self):
        self.assertEqual(chunk_text("", max_len=10), [])
        self.assertEqual(chunk_text(" \n\t ", max_len=10), [])
        for limit in (0, -1):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    chunk_text("text", max_len=limit)
        with self.assertRaises(TypeError):
            chunk_text("text", max_len=1.5)
        with self.assertRaises(TypeError):
            chunk_text("text", max_len=True)
        with self.assertRaises(TypeError):
            chunk_text(123, max_len=10)


if __name__ == "__main__":
    unittest.main()
