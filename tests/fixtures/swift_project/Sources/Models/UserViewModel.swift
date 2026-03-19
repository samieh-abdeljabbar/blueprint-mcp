import Foundation

class UserViewModel: ObservableObject {
    @Published var users: [User] = []

    func loadUsers() {
        // load users
    }
}
