import SwiftUI

@Observable
final class ChatDetailViewModel {
    var messages: [Message] = []
    var isLoading = false
    var isSending = false
    var error: String?
    var isAssistantMonitoring = true

    let conversationId: String
    private let apiClient = APIClient.shared
    private var pollTimer: Timer?

    init(conversationId: String) {
        self.conversationId = conversationId
    }

    func load() async {
        isLoading = true
        error = nil

        do {
            messages = try await apiClient.get(
                "/api/mobile/conversations/\(conversationId)/messages",
                queryItems: [URLQueryItem(name: "limit", value: "50")]
            )
        } catch {
            // Fall back to mock data
            messages = Message.mockMessages
        }

        isLoading = false
    }

    func sendMessage(_ body: String) async {
        guard !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }

        isSending = true
        let request = SendMessageRequest(body: body)

        do {
            let newMessage: Message = try await apiClient.post(
                "/api/mobile/conversations/\(conversationId)/messages",
                body: request
            )
            messages.append(newMessage)
        } catch {
            // Create an optimistic local message
            let localMessage = Message(
                id: UUID().uuidString,
                conversationId: conversationId,
                body: body,
                sender: .agent,
                createdAt: Date()
            )
            messages.append(localMessage)
        }

        isSending = false
    }

    func pollForNewMessages() async {
        do {
            let newMessages: [Message] = try await apiClient.get(
                "/api/mobile/conversations/\(conversationId)/messages",
                queryItems: [URLQueryItem(name: "limit", value: "50")]
            )
            messages = newMessages
        } catch {
            // Silently ignore poll failures
        }
    }
}

struct ChatDetailView: View {
    let conversationId: String
    let contactName: String
    let contactInitials: String
    let contactAvatarColor: String

    @State private var viewModel: ChatDetailViewModel
    @State private var messageText = ""
    @State private var pollTask: Task<Void, Never>?

    init(conversationId: String, contactName: String, contactInitials: String, contactAvatarColor: String) {
        self.conversationId = conversationId
        self.contactName = contactName
        self.contactInitials = contactInitials
        self.contactAvatarColor = contactAvatarColor
        self._viewModel = State(initialValue: ChatDetailViewModel(conversationId: conversationId))
    }

    var body: some View {
        VStack(spacing: 0) {
            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: CallowaySpacing.lg) {
                        ForEach(viewModel.messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
                    }
                    .padding(.horizontal, CallowaySpacing.lg)
                    .padding(.vertical, CallowaySpacing.md)
                }
                .onChange(of: viewModel.messages.count) { _, _ in
                    if let lastMessage = viewModel.messages.last {
                        withAnimation {
                            proxy.scrollTo(lastMessage.id, anchor: .bottom)
                        }
                    }
                }
            }

            // Monitoring banner
            if viewModel.isAssistantMonitoring {
                HStack(spacing: CallowaySpacing.sm) {
                    Image(systemName: "eye.fill")
                        .font(.system(size: 13))
                    Text("Assistant is actively monitoring this thread.")
                        .font(CallowayFonts.caption)
                }
                .foregroundStyle(CallowayColors.amber)
                .padding(.vertical, CallowaySpacing.sm)
                .padding(.horizontal, CallowaySpacing.lg)
                .frame(maxWidth: .infinity)
                .background(CallowayColors.amberBackground)
            }

            // Input bar
            HStack(spacing: CallowaySpacing.md) {
                TextField("Take over conversation...", text: $messageText)
                    .font(CallowayFonts.body)
                    .foregroundStyle(CallowayColors.textPrimary)
                    .padding(.horizontal, CallowaySpacing.md)
                    .padding(.vertical, CallowaySpacing.sm)
                    .background(CallowayColors.inputBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 20))
                    .overlay(
                        RoundedRectangle(cornerRadius: 20)
                            .stroke(CallowayColors.cardBorder, lineWidth: 1)
                    )

                Button {
                    let text = messageText
                    messageText = ""
                    Task {
                        await viewModel.sendMessage(text)
                    }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 32))
                        .foregroundStyle(
                            messageText.isEmpty ? CallowayColors.textTertiary : CallowayColors.primaryAccent
                        )
                }
                .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .buttonStyle(.plain)
            }
            .padding(.horizontal, CallowaySpacing.lg)
            .padding(.vertical, CallowaySpacing.sm)
            .background(CallowayColors.background)
        }
        .background(CallowayColors.background)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                HStack(spacing: CallowaySpacing.sm) {
                    AvatarView(
                        initials: contactInitials,
                        colorHex: contactAvatarColor,
                        size: 32
                    )
                    VStack(alignment: .leading, spacing: 0) {
                        Text(contactName)
                            .font(CallowayFonts.subheadline)
                            .foregroundStyle(CallowayColors.textPrimary)
                        Text("Assistant handling")
                            .font(CallowayFonts.caption)
                            .foregroundStyle(CallowayColors.textSecondary)
                    }
                }
            }
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button { } label: {
                    Image(systemName: "phone")
                        .foregroundStyle(CallowayColors.textPrimary)
                }
                Button { } label: {
                    Image(systemName: "video")
                        .foregroundStyle(CallowayColors.textPrimary)
                }
            }
        }
        .toolbarBackground(CallowayColors.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .task {
            await viewModel.load()
        }
        .onAppear {
            // Start polling every 5 seconds
            pollTask = Task {
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(5))
                    if !Task.isCancelled {
                        await viewModel.pollForNewMessages()
                    }
                }
            }
        }
        .onDisappear {
            pollTask?.cancel()
        }
    }
}

#Preview("Dark") {
    NavigationStack {
        ChatDetailView(
            conversationId: "conv-001",
            contactName: "John Doe",
            contactInitials: "JD",
            contactAvatarColor: "#4F46E5"
        )
    }
    .preferredColorScheme(.dark)
}

#Preview("Light") {
    NavigationStack {
        ChatDetailView(
            conversationId: "conv-001",
            contactName: "John Doe",
            contactInitials: "JD",
            contactAvatarColor: "#4F46E5"
        )
    }
    .preferredColorScheme(.light)
}
