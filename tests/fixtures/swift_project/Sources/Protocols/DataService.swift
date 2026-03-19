import Foundation

protocol DataService {
    func fetchData() async throws -> [User]
}

class NetworkDataService: DataService {
    func fetchData() async throws -> [User] {
        return []
    }
}

enum AppError: Error {
    case networkError
    case decodingError
    case unauthorized
}
