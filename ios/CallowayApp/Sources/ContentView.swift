import SwiftUI

/// Root view — placeholder to validate the build pipeline.
struct ContentView: View {
    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "house.fill")
                .font(.system(size: 64))
                .foregroundStyle(.blue)

            Text("Calloway")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text("AI Assistant for Real Estate Agents")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Text("Pipeline test — if you see this, it works.")
                .font(.caption)
                .padding(.top, 40)
                .foregroundStyle(.tertiary)
        }
        .padding()
    }
}

#Preview {
    ContentView()
}
