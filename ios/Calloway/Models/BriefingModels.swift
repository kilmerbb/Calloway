import Foundation

// MARK: - API Response Models

struct BriefingResponse: Codable, Sendable {
    let greeting: String
    let date: String
    let summaryItems: [String]
    let totalChats: Int
    let eventsCount: Int

    enum CodingKeys: String, CodingKey {
        case greeting
        case date
        case summaryItems = "summary_items"
        case totalChats = "total_chats"
        case eventsCount = "events_count"
    }
}

struct ScheduleEvent: Codable, Identifiable, Sendable {
    let id: String
    let time: String
    let type: String
    let address: String
    let contactName: String

    enum CodingKeys: String, CodingKey {
        case id
        case time
        case type
        case address
        case contactName = "contact_name"
    }
}

// MARK: - Mock Data

extension BriefingResponse {
    static let mock = BriefingResponse(
        greeting: "Good morning, Alex.",
        date: "SATURDAY, MARCH 21ST",
        summaryItems: [
            "Responded to 3 new leads overnight",
            "Confirmed showing with Sarah Jenkins at 10 AM",
            "Sent follow-up to Mike Thompson about appraisal",
            "Scheduled open house reminder for Sunday"
        ],
        totalChats: 12,
        eventsCount: 3
    )
}

extension ScheduleEvent {
    static let mockEvents: [ScheduleEvent] = [
        ScheduleEvent(
            id: "evt-001",
            time: "10:00 AM",
            type: "Showing",
            address: "123 Maple Street",
            contactName: "Sarah Jenkins"
        ),
        ScheduleEvent(
            id: "evt-002",
            time: "1:30 PM",
            type: "Appraisal",
            address: "847 Oak Avenue",
            contactName: "Mike Thompson"
        ),
        ScheduleEvent(
            id: "evt-003",
            time: "3:00 PM",
            type: "Showing",
            address: "442 Pine Lane",
            contactName: "David & Emma Reed"
        )
    ]
}
