import Foundation

struct User: Codable, Identifiable {
    let id: UUID
    var name: String
    var email: String
}
