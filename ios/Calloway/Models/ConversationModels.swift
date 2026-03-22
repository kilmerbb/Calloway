import Foundation

// MARK: - Conversation List

struct ConversationListItem: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let contactName: String
    let contactAvatarURL: String?
    let contactInitials: String
    let avatarColor: String
    let lastMessagePreview: String
    let lastMessageAt: Date
    let unreadCount: Int
    let isOnline: Bool
    let isBotHandled: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case contactName = "contact_name"
        case contactAvatarURL = "contact_avatar_url"
        case contactInitials = "contact_initials"
        case avatarColor = "avatar_color"
        case lastMessagePreview = "last_message_preview"
        case lastMessageAt = "last_message_at"
        case unreadCount = "unread_count"
        case isOnline = "is_online"
        case isBotHandled = "is_bot_handled"
    }
}

// MARK: - Message

struct Message: Codable, Identifiable, Sendable {
    let id: String
    let conversationId: String
    let body: String
    let sender: MessageSender
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case conversationId = "conversation_id"
        case body
        case sender
        case createdAt = "created_at"
    }
}

enum MessageSender: String, Codable, Sendable {
    case contact
    case assistant
    case agent
}

// MARK: - Send Message

struct SendMessageRequest: Codable, Sendable {
    let body: String
}

// MARK: - Unread Count

struct UnreadCountResponse: Codable, Sendable {
    let count: Int
}

// MARK: - Chat Filter

enum ChatFilter: String, CaseIterable {
    case all = "All Chats"
    case unread = "Unread"
    case botHandled = "Bot Handled"

    var queryValue: String {
        switch self {
        case .all: return "all"
        case .unread: return "unread"
        case .botHandled: return "bot_handled"
        }
    }

    var iconName: String? {
        switch self {
        case .botHandled: return "cpu"
        default: return nil
        }
    }
}

// MARK: - Contact

struct Contact: Codable, Identifiable, Sendable {
    let id: String
    let name: String
    let avatarURL: String?
    let initials: String
    let avatarColor: String

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case avatarURL = "avatar_url"
        case initials
        case avatarColor = "avatar_color"
    }
}

// MARK: - Relative Timestamps

extension Date {
    func relativeTimestamp() -> String {
        let now = Date()
        let interval = now.timeIntervalSince(self)

        if interval < 60 {
            return "just now"
        } else if interval < 3600 {
            let minutes = Int(interval / 60)
            return "\(minutes) minute\(minutes == 1 ? "" : "s") ago"
        } else if interval < 86400 {
            let hours = Int(interval / 3600)
            return "about \(hours) hour\(hours == 1 ? "" : "s") ago"
        } else if interval < 604800 {
            let days = Int(interval / 86400)
            return "\(days) day\(days == 1 ? "" : "s") ago"
        } else {
            let formatter = DateFormatter()
            formatter.dateStyle = .short
            return formatter.string(from: self)
        }
    }
}

// MARK: - Mock Data

extension ConversationListItem {
    static let mockConversations: [ConversationListItem] = [
        ConversationListItem(
            id: "conv-001",
            contactName: "John Doe",
            contactAvatarURL: nil,
            contactInitials: "JD",
            avatarColor: "#4F46E5",
            lastMessagePreview: "Thanks for confirming the showing time. I'll be there at 10.",
            lastMessageAt: Date().addingTimeInterval(-480),
            unreadCount: 2,
            isOnline: true,
            isBotHandled: true
        ),
        ConversationListItem(
            id: "conv-002",
            contactName: "Sarah Jenkins",
            contactAvatarURL: nil,
            contactInitials: "SJ",
            avatarColor: "#DC2626",
            lastMessagePreview: "Can we reschedule the showing to next Tuesday?",
            lastMessageAt: Date().addingTimeInterval(-7200),
            unreadCount: 0,
            isOnline: false,
            isBotHandled: true
        ),
        ConversationListItem(
            id: "conv-003",
            contactName: "Mike Thompson",
            contactAvatarURL: nil,
            contactInitials: "MT",
            avatarColor: "#059669",
            lastMessagePreview: "The appraisal report should be ready by Friday.",
            lastMessageAt: Date().addingTimeInterval(-14400),
            unreadCount: 1,
            isOnline: true,
            isBotHandled: false
        ),
        ConversationListItem(
            id: "conv-004",
            contactName: "David & Emma Reed",
            contactAvatarURL: nil,
            contactInitials: "DR",
            avatarColor: "#D97706",
            lastMessagePreview: "We loved the house on Pine Lane! What's the next step?",
            lastMessageAt: Date().addingTimeInterval(-86400),
            unreadCount: 0,
            isOnline: false,
            isBotHandled: true
        )
    ]
}

extension Message {
    static let mockMessages: [Message] = [
        Message(
            id: "msg-001",
            conversationId: "conv-001",
            body: "Hi, I'm interested in the property at 123 Maple Street. Is it still available?",
            sender: .contact,
            createdAt: Date().addingTimeInterval(-3600)
        ),
        Message(
            id: "msg-002",
            conversationId: "conv-001",
            body: "Hi John! Yes, 123 Maple Street is still available. It's a beautiful 3-bedroom home listed at $425,000. Would you like to schedule a showing? I have availability this week.",
            sender: .assistant,
            createdAt: Date().addingTimeInterval(-3540)
        ),
        Message(
            id: "msg-003",
            conversationId: "conv-001",
            body: "That sounds great! How about tomorrow at 10 AM?",
            sender: .contact,
            createdAt: Date().addingTimeInterval(-3000)
        ),
        Message(
            id: "msg-004",
            conversationId: "conv-001",
            body: "Tomorrow at 10 AM works perfectly. I've scheduled the showing for 123 Maple Street. I'll send you a confirmation with the full address and directions shortly.",
            sender: .assistant,
            createdAt: Date().addingTimeInterval(-2940)
        ),
        Message(
            id: "msg-005",
            conversationId: "conv-001",
            body: "Thanks for confirming the showing time. I'll be there at 10.",
            sender: .contact,
            createdAt: Date().addingTimeInterval(-480)
        )
    ]
}
