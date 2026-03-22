import SwiftUI

enum AppTab: String, CaseIterable {
    case briefing = "Briefing"
    case chats = "Chats"
    case content = "Content"

    var iconName: String {
        switch self {
        case .briefing: return "square.grid.2x2"
        case .chats: return "bubble.left.and.bubble.right"
        case .content: return "photo"
        }
    }
}

struct MainTabView: View {
    @State private var selectedTab: AppTab = .briefing
    @State private var unreadCount = 0

    private let apiClient = APIClient.shared

    var body: some View {
        TabView(selection: $selectedTab) {
            BriefingView(onViewAllChats: {
                selectedTab = .chats
            })
            .tabItem {
                Label(AppTab.briefing.rawValue, systemImage: AppTab.briefing.iconName)
            }
            .tag(AppTab.briefing)

            ChatsListView()
                .tabItem {
                    Label(AppTab.chats.rawValue, systemImage: AppTab.chats.iconName)
                }
                .tag(AppTab.chats)
                .badge(unreadCount > 0 ? unreadCount : 0)

            ContentPortalView()
                .tabItem {
                    Label(AppTab.content.rawValue, systemImage: AppTab.content.iconName)
                }
                .tag(AppTab.content)
        }
        .tint(CallowayColors.primaryAccent)
        .onAppear {
            configureTabBarAppearance()
        }
        .task {
            await fetchUnreadCount()
        }
    }

    private func configureTabBarAppearance() {
        let appearance = UITabBarAppearance()
        appearance.configureWithOpaqueBackground()
        appearance.backgroundColor = UIColor(CallowayColors.tabBarBackground)

        let itemAppearance = UITabBarItemAppearance()
        itemAppearance.normal.iconColor = UIColor(CallowayColors.textTertiary)
        itemAppearance.normal.titleTextAttributes = [.foregroundColor: UIColor(CallowayColors.textTertiary)]
        itemAppearance.selected.iconColor = UIColor(CallowayColors.primaryAccent)
        itemAppearance.selected.titleTextAttributes = [.foregroundColor: UIColor(CallowayColors.primaryAccent)]

        appearance.stackedLayoutAppearance = itemAppearance
        appearance.inlineLayoutAppearance = itemAppearance
        appearance.compactInlineLayoutAppearance = itemAppearance

        UITabBar.appearance().standardAppearance = appearance
        UITabBar.appearance().scrollEdgeAppearance = appearance
    }

    private func fetchUnreadCount() async {
        do {
            let response: UnreadCountResponse = try await apiClient.get(
                "/api/mobile/conversations/unread-count"
            )
            unreadCount = response.count
        } catch {
            // Silently fail — badge just won't show
        }
    }
}

#Preview {
    MainTabView()
        .preferredColorScheme(.dark)
}
