import { BaseClient } from './BaseClient';

class ApiClient extends BaseClient {
    async getUsers() {
        return this.get('/users');
    }
}

export default ApiClient;
