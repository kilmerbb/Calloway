import Foundation

// MARK: - Auth Models

struct LoginRequest: Codable, Sendable {
    let email: String
    let password: String
}

struct AuthResponse: Codable, Sendable {
    let token: String
    let refreshToken: String
    let agent: AgentProfile

    enum CodingKeys: String, CodingKey {
        case token
        case refreshToken = "refresh_token"
        case agent
    }
}

struct RefreshRequest: Codable, Sendable {
    let refreshToken: String

    enum CodingKeys: String, CodingKey {
        case refreshToken = "refresh_token"
    }
}

struct RefreshResponse: Codable, Sendable {
    let token: String
}

struct AgentProfile: Codable, Sendable {
    let id: String
    let name: String
    let email: String
}

// MARK: - Auth Service

@Observable
final class AuthService {
    static let shared = AuthService()

    private let apiClient = APIClient.shared

    var isAuthenticated: Bool {
        apiClient.isAuthenticated
    }

    var currentAgent: AgentProfile? {
        guard let data = UserDefaults.standard.data(forKey: "calloway_agent_profile") else {
            return nil
        }
        return try? JSONDecoder().decode(AgentProfile.self, from: data)
    }

    func login(email: String, password: String) async throws {
        let request = LoginRequest(email: email, password: password)
        let response: AuthResponse = try await apiClient.post(
            "/api/mobile/auth/login",
            body: request,
            authenticated: false
        )
        apiClient.token = response.token
        apiClient.refreshToken = response.refreshToken

        if let agentData = try? JSONEncoder().encode(response.agent) {
            UserDefaults.standard.set(agentData, forKey: "calloway_agent_profile")
        }
    }

    func refreshTokenIfNeeded() async throws {
        guard let refreshToken = apiClient.refreshToken else {
            throw APIError.unauthorized
        }
        let request = RefreshRequest(refreshToken: refreshToken)
        let response: RefreshResponse = try await apiClient.post(
            "/api/mobile/auth/refresh",
            body: request,
            authenticated: false
        )
        apiClient.token = response.token
    }

    func logout() {
        apiClient.clearTokens()
        UserDefaults.standard.removeObject(forKey: "calloway_agent_profile")
    }
}
