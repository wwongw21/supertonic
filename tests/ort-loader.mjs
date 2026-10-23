const fakeRuntimeUrl = new URL('./fake-onnxruntime.mjs', import.meta.url).href;

export async function resolve(specifier, context, nextResolve) {
    if (specifier === 'onnxruntime-node' || specifier === 'onnxruntime-web') {
        return { url: fakeRuntimeUrl, shortCircuit: true };
    }
    return nextResolve(specifier, context);
}

export async function load(url, context, nextLoad) {
    const loaded = await nextLoad(url, context);
    if (url.endsWith('/nodejs/helper.js')) {
        const source = typeof loaded.source === 'string'
            ? loaded.source
            : new TextDecoder().decode(loaded.source);
        const transformed = source.includes('export class TextToSpeech {')
            ? source
            : source.replace('class TextToSpeech {', 'export class TextToSpeech {');
        if (transformed === source && !source.includes('export class TextToSpeech {')) {
            throw new Error('test linker could not expose the internal Node helper class');
        }
        return { ...loaded, source: transformed, shortCircuit: true };
    }
    return loaded;
}
