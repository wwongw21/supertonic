export class Tensor {
    constructor(type, data, dims) {
        this.type = type;
        this.data = data;
        this.dims = dims;
    }
}

export class InferenceSession {}
export const env = { wasm: {} };
