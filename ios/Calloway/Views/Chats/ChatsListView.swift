import SwiftUI

@Observable
final class ChatsListViewModel {
    var conversations: [ConversationListItem] = []
    var selectedFilter: ChatFilter = .all
    var searchText = ""
    var isLoading = false
    var error: String?

    private let apiClient = APIClient.shared

    var filteredConversations: [ConversationListItem] {
        var result = conversations

        switch selectedFilter {
        case .all:
            break
        case .unread:
            result = result.filter { $0.unreadCount > 0 }
        case .botHandled:
            result = result.filter { $0.isBotHandled }
        }

        if !searchText.isEmpty {
            result = result.filter {
                $0.contactName.localizedCaseInsensitiveContains(searchText) ||
                $0.lastMessagePreview.localizedCaseInsensitiveContains(searchText)
            }
        }

        return result
    }

    func load() async {
        isLoading = true
        error = nil

        do {
            var queryItems: [URLQueryItem] = [
                URLQueryItem(name: "filter", value: selectedFilter.queryValue)
            ]
            if !searchText.isEmpty {
                queryItems.append(URLQueryItem(name: "search", value: searchText))
            }
            conversations = try await apiClient.get(
                "/api/mobile/conversations",
                queryItems: queryItems
            )
        } catch {
            // Fall back to mock data
            conversations = ConversationListItem.mockConversations
        }

        isLoading = false
    }

    func loadMock() {
        conversations = ConversationListItem.mockConversations
    }
}

struct ChatsListView: View {
    @State private var viewModel = ChatsListViewModel()
    @State private var searchText = ""

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Header
                VStack(alignment: .leading, spacing: CallowaySpacing.lg) {
                    Text("Assistant Chats")
                        .font(CallowayFonts.largeTitle)
                        .foregroundStyle(CallowayColors.textPrimary)
                        .padding(.horizontal, CallowaySpacing.lg)

                    // Search bar
                    HStack(spacing: CallowaySpacing.sm) {
                        Image(systemName: "magnifyingglass")
                            .foregroundStyle(CallowayColors.textTertiary)
                        TextField("Search conversations...", text: $searchText)
                            .font(CallowayFonts.body)
                            .foregroundStyle(CallowayColors.textPrimary)
                    }
                    .padding(CallowaySpacing.md)
                    .background(CallowayColors.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .padding(.horizontal, CallowaySpacing.lg)
                    .onChange(of: searchText) { _, newValue in
                        viewModel.searchText = newValue
                    }

                    // Filter chips
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: CallowaySpacing.sm) {
                            ForEach(ChatFilter.allCases, id: \.self) { filter in
                                FilterChip(
                                    label: filter.rawValue,
                                    isSelected: viewModel.selectedFilter == filter,
                                    iconName: filter.iconName
                                ) {
                                    viewModel.selectedFilter = filter
                                }
                            }
                        }
                        .padding(.horizontal, CallowaySpacing.lg)
                    }
                }
                .padding(.top, CallowaySpacing.md)
                .padding(.bottom, CallowaySpacing.md)

                // Conversation list
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(viewModel.filteredConversations) { conversation in
                            NavigationLink(value: conversation) {
                                ConversationCard(conversation: conversation)
                            }
                            .buttonStyle(.plain)

                            if conversation.id != viewModel.filteredConversations.last?.id {
                                Divider()
                                    .background(CallowayColors.cardBorder)
                                    .padding(.leading, 76)
                            }
                        }
                    }
                }
                .refreshable {
                    await viewModel.load()
                }
            }
            .background(CallowayColors.background)
            .navigationDestination(for: ConversationListItem.self) { conversation in
                ChatDetailView(
                    conversationId: conversation.id,
                    contactName: conversation.contactName,
                    contactInitials: conversation.contactInitials,
                    contactAvatarColor: conversation.avatarColor
                )
            }
            .task {
                if viewModel.conversations.isEmpty {
                    await viewModel.load()
                }
            }
        }
    }
}

#Preview("Dark") {
    ChatsListView()
        .preferredColorScheme(.dark)
}

#Preview("Light") {
    ChatsListView()
        .preferredColorScheme(.light)
}
