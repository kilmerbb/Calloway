import Foundation

// MARK: - Listing

struct Listing: Codable, Identifiable, Sendable {
    let id: String
    let address: String
    let price: Double
    let beds: Int
    let baths: Double
    let description: String
    let mediaURLs: [String]
    let status: ListingStatus
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case address
        case price
        case beds
        case baths
        case description
        case mediaURLs = "media_urls"
        case status
        case createdAt = "created_at"
    }
}

enum ListingStatus: String, Codable, Sendable {
    case draft
    case active
    case pending
    case sold
}

// MARK: - Create Listing Request

struct CreateListingRequest: Codable, Sendable {
    let address: String
    let price: Double
    let beds: Int
    let baths: Double
    let description: String
}

// MARK: - Content Tab

enum ContentTab: String, CaseIterable {
    case newListing = "New Listing"
    case myContent = "My Content"
}

// MARK: - Mock Data

extension Listing {
    static let mockListings: [Listing] = [
        Listing(
            id: "lst-001",
            address: "123 Maple Street, Springfield",
            price: 425000,
            beds: 3,
            baths: 2.5,
            description: "Beautiful colonial home with updated kitchen and spacious backyard.",
            mediaURLs: [],
            status: .active,
            createdAt: Date().addingTimeInterval(-172800)
        ),
        Listing(
            id: "lst-002",
            address: "847 Oak Avenue, Riverside",
            price: 550000,
            beds: 4,
            baths: 3,
            description: "Modern farmhouse style with open concept living and premium finishes.",
            mediaURLs: [],
            status: .active,
            createdAt: Date().addingTimeInterval(-86400)
        ),
        Listing(
            id: "lst-003",
            address: "442 Pine Lane, Lakewood",
            price: 375000,
            beds: 2,
            baths: 2,
            description: "Charming bungalow near the lake with stunning sunset views.",
            mediaURLs: [],
            status: .draft,
            createdAt: Date().addingTimeInterval(-3600)
        )
    ]
}
