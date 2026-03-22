import SwiftUI

@main
struct CallowayApp: App {
    @State private var authService = AuthService.shared

    var body: some Scene {
        WindowGroup {
            Group {
                if authService.isAuthenticated {
                    MainTabView()
                } else {
                    LoginView()
                }
            }
            .preferredColorScheme(.dark)
        }
    }
}

// MARK: - Login View

struct LoginView: View {
    @State private var email = ""
    @State private var password = ""
    @State private var isLoading = false
    @State private var error: String?

    private let authService = AuthService.shared

    var body: some View {
        VStack(spacing: CallowaySpacing.xxxl) {
            Spacer()

            // Logo / Brand
            VStack(spacing: CallowaySpacing.md) {
                Image(systemName: "building.2")
                    .font(.system(size: 48))
                    .foregroundStyle(CallowayColors.primaryAccent)

                Text("Calloway")
                    .font(.system(size: 34, weight: .bold))
                    .foregroundStyle(CallowayColors.textPrimary)

                Text("AI Assistant for Real Estate")
                    .font(CallowayFonts.body)
                    .foregroundStyle(CallowayColors.textSecondary)
            }

            // Form
            VStack(spacing: CallowaySpacing.lg) {
                VStack(alignment: .leading, spacing: CallowaySpacing.xs) {
                    Text("EMAIL")
                        .font(CallowayFonts.label)
                        .foregroundStyle(CallowayColors.textTertiary)
                        .tracking(0.8)

                    TextField("agent@example.com", text: $email)
                        .font(CallowayFonts.body)
                        .foregroundStyle(CallowayColors.textPrimary)
                        .textContentType(.emailAddress)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .padding(CallowaySpacing.md)
                        .background(CallowayColors.inputBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(CallowayColors.cardBorder, lineWidth: 1)
                        )
                }

                VStack(alignment: .leading, spacing: CallowaySpacing.xs) {
                    Text("PASSWORD")
                        .font(CallowayFonts.label)
                        .foregroundStyle(CallowayColors.textTertiary)
                        .tracking(0.8)

                    SecureField("Enter your password", text: $password)
                        .font(CallowayFonts.body)
                        .foregroundStyle(CallowayColors.textPrimary)
                        .textContentType(.password)
                        .padding(CallowaySpacing.md)
                        .background(CallowayColors.inputBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(CallowayColors.cardBorder, lineWidth: 1)
                        )
                }

                if let error = error {
                    Text(error)
                        .font(CallowayFonts.caption)
                        .foregroundStyle(.red)
                }

                Button {
                    Task {
                        isLoading = true
                        error = nil
                        do {
                            try await authService.login(email: email, password: password)
                        } catch {
                            self.error = error.localizedDescription
                        }
                        isLoading = false
                    }
                } label: {
                    Group {
                        if isLoading {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Text("Sign In")
                                .font(CallowayFonts.headline)
                        }
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, CallowaySpacing.md)
                    .background(CallowayColors.primaryAccent)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .disabled(email.isEmpty || password.isEmpty || isLoading)
                .opacity(email.isEmpty || password.isEmpty ? 0.6 : 1.0)
            }
            .padding(.horizontal, CallowaySpacing.xxl)

            Spacer()
            Spacer()
        }
        .background(CallowayColors.background)
    }
}

#Preview("Login") {
    LoginView()
        .preferredColorScheme(.dark)
}

#Preview("Main App") {
    MainTabView()
        .preferredColorScheme(.dark)
}
