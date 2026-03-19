import SwiftUI

struct ContentView: View {
    @StateObject var viewModel = UserViewModel()

    var body: some View {
        List(viewModel.users) { user in
            Text(user.name)
        }
    }
}
