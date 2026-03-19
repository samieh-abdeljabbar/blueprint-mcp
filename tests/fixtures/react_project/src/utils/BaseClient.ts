export class BaseClient {
    baseUrl: string;

    constructor(baseUrl: string = '/api') {
        this.baseUrl = baseUrl;
    }

    async get(path: string) {
        return fetch(this.baseUrl + path);
    }

    async post(path: string, body: any) {
        return fetch(this.baseUrl + path, {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }
}
