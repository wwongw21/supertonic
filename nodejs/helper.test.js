import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { TextToSpeech, loadVoiceStyle } from './helper.js';

const style = { ttl: { dims: [1] } };
const voiceStyle = {
    style_ttl: { dims: [1, 1, 2], data: [[0.25, 0.5]] },
    style_dp: { dims: [1, 1, 2], data: [[0.75, 1.0]] }
};

test('loadVoiceStyle works before model loading', () => {
    const directory = mkdtempSync(join(tmpdir(), 'supertonic-style-first-'));
    const voiceStylePath = join(directory, 'voice.json');
    writeFileSync(voiceStylePath, JSON.stringify(voiceStyle));
    try {
        const loadedStyle = loadVoiceStyle([voiceStylePath]);
        assert.deepEqual(loadedStyle.ttl.dims, [1, 1, 2]);
        assert.deepEqual(Array.from(loadedStyle.ttl.data), [0.25, 0.5]);
        assert.deepEqual(loadedStyle.dp.dims, [1, 1, 2]);
    } finally {
        rmSync(directory, { recursive: true, force: true });
    }
});

function fakeTts(responses, sampleRate = 10) {
    const tts = Object.create(TextToSpeech.prototype);
    tts.sampleRate = sampleRate;
    tts._infer = async () => {
        const response = responses.shift();
        if (!response) {
            throw new Error('not enough fake inference responses');
        }
        return response;
    };
    return tts;
}

test('trims both padded chunks before concatenating', async () => {
    const tts = fakeTts([
        { wav: [1, 1, 1, 0, 0], duration: [0.3] },
        { wav: [2, 2, 2, 0, 0], duration: [0.3] }
    ]);

    const result = await tts.call('A sentence. '.repeat(40), 'en', style, 1, 1.0, 0);

    assert.deepEqual(result.wav, [1, 1, 1, 2, 2, 2]);
    assert.deepEqual(result.duration, [0.6]);
});

test('keeps odd-length chunks, exact silence, and the final samples over four chunks', async () => {
    const tts = fakeTts([
        { wav: [1, 1, 1, 0, 0, 0], duration: [0.3] },
        { wav: [2, 2, 2, 0, 0], duration: [0.3] },
        { wav: [3, 3, 3, 0], duration: [0.35] },
        { wav: [4, 4, 4, 4, 0, 0], duration: [0.4] }
    ]);

    const result = await tts.call('x. '.repeat(400), 'en', style, 1, 1.0, 0.15);

    assert.deepEqual(
        result.wav,
        [1, 1, 1, 0, 2, 2, 2, 0, 3, 3, 3, 0, 4, 4, 4, 4]
    );
    assert.deepEqual(result.duration, [1.6]);
});

test('clamps predicted sample count to the available waveform', async () => {
    const tts = fakeTts([{ wav: [7, 8, 9], duration: [0.8] }]);

    const result = await tts.call('A short sentence.', 'en', style, 1, 1.0, 0);

    assert.deepEqual(result.wav, [7, 8, 9]);
    assert.deepEqual(result.duration, [0.3]);
});

test('empty input returns an empty waveform with zero duration', async () => {
    const tts = fakeTts([]);

    const result = await tts.call(' \n\t ', 'en', style, 1);

    assert.deepEqual(result, { wav: [], duration: [0] });
});

test('rejects negative or nonfinite silence duration', async () => {
    const tts = fakeTts([{ wav: [1, 2, 0], duration: [0.2] }]);

    await assert.rejects(
        tts.call('A short sentence.', 'en', style, 1, 1.0, -0.1),
        RangeError
    );
    await assert.rejects(
        tts.call('A short sentence.', 'en', style, 1, 1.0, Infinity),
        RangeError
    );
});

test('batch results retain their independent row layout', async () => {
    const rows = [[11, 12, 0, 0], [21, 22, 23, 0]];
    const durations = [0.2, 0.3];
    const tts = fakeTts([{ wav: rows, duration: durations }]);

    const result = await tts.batch(['one', 'two'], ['en', 'en'], style, 1);

    assert.deepEqual(result, { wav: rows, duration: durations });
});
