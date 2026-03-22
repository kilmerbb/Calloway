import Foundation

// MARK: - API Client

@Observable
final class APIClient: Sendable {
    static let shared = APIClient()

    private let baseURL: String
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    private static let tokenKey = "calloway_auth_token"
    private static let refreshTokenKey = "calloway_refresh_token"

    init(baseURL: String = "http://localhost:8000") {
        self.baseURL = baseURL
        self.session = URLSession.shared

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder
    }

    // MARK: - Token Management

    var token: String? {
        get { UserDefaults.standard.string(forKey: Self.tokenKey) }
        set { UserDefaults.standard.set(newValue, forKey: Self.tokenKey) }
    }

    var refreshToken: String? {
        get { UserDefaults.standard.string(forKey: Self.refreshTokenKey) }
        set { UserDefaults.standard.set(newValue, forKey: Self.refreshTokenKey) }
    }

    var isAuthenticated: Bool {
        token != nil
    }

    func clearTokens() {
        UserDefaults.standard.removeObject(forKey: Self.tokenKey)
        UserDefaults.standard.removeObject(forKey: Self.refreshTokenKey)
    }

    // MARK: - Request Building

    private func buildURL(path: String, queryItems: [URLQueryItem]? = nil) throws -> URL {
        var components = URLComponents(string: "\(baseURL)\(path)")
        components?.queryItems = queryItems?.isEmpty == true ? nil : queryItems
        guard let url = components?.url else {
            throw APIError.invalidURL
        }
        return url
    }

    private func buildRequest(
        url: URL,
        method: String,
        body: (any Encodable)? = nil,
        authenticated: Bool = true
    ) throws -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if authenticated, let token = token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body = body {
            request.httpBody = try encoder.encode(body)
        }

        return request
    }

    // MARK: - Generic Request Methods

    func get<T: Decodable>(
        _ path: String,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> T {
        let url = try buildURL(path: path, queryItems: queryItems)
        let request = try buildRequest(url: url, method: "GET")
        return try await execute(request)
    }

    func post<T: Decodable>(
        _ path: String,
        body: (any Encodable)? = nil,
        authenticated: Bool = true
    ) async throws -> T {
        let url = try buildURL(path: path)
        let request = try buildRequest(url: url, method: "POST", body: body, authenticated: authenticated)
        return try await execute(request)
    }

    // MARK: - Execution

    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            return try decoder.decode(T.self, from: data)
        case 401:
            clearTokens()
            throw APIError.unauthorized
        case 404:
            throw APIError.notFound
        case 422:
            throw APIError.validationError
        default:
            throw APIError.serverError(httpResponse.statusCode)
        }
    }
}

// MARK: - API Error

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case notFound
    case validationError
    case serverError(Int)
    case decodingError(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .unauthorized:
            return "Session expired. Please log in again."
        case .notFound:
            return "Resource not found"
        case .validationError:
            return "Invalid request data"
        case .serverError(let code):
            return "Server error (\(code))"
        case .decodingError(let error):
            return "Data parsing error: \(error.localizedDescription)"
        }
    }
}
