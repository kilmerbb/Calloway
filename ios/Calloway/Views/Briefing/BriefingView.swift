import SwiftUI

@Observable
final class BriefingViewModel {
    var briefing: BriefingResponse?
    var events: [ScheduleEvent] = []
    var isLoading = false
    var error: String?

    private let apiClient = APIClient.shared

    func load() async {
        isLoading = true
        error = nil

        // In production, these would be real API calls.
        // Using mock data for preview compatibility.
        do {
            async let briefingResult: BriefingResponse = apiClient.get("/api/mobile/briefing")
            async let eventsResult: [ScheduleEvent] = apiClient.get("/api/mobile/schedule")
            let (b, e) = try await (briefingResult, eventsResult)
            briefing = b
            events = e
        } catch {
            // Fall back to mock data if API is unavailable
            briefing = .mock
            events = ScheduleEvent.mockEvents
        }

        isLoading = false
    }

    func loadMock() {
        briefing = .mock
        events = ScheduleEvent.mockEvents
    }
}

struct BriefingView: View {
    @State private var viewModel = BriefingViewModel()
    var onViewAllChats: (() -> Void)? = nil

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: CallowaySpacing.xl) {
                // Header
                VStack(alignment: .leading, spacing: CallowaySpacing.xs) {
                    Text("Daily Briefing")
                        .font(CallowayFonts.largeTitle)
                        .foregroundStyle(CallowayColors.textPrimary)

                    Text(viewModel.briefing?.date ?? "TODAY")
                        .font(CallowayFonts.label)
                        .foregroundStyle(CallowayColors.primaryAccent)
                        .tracking(1.2)
                }

                // Greeting
                if let greeting = viewModel.briefing?.greeting {
                    Text(greeting)
                        .font(.system(size: 24, weight: .bold))
                        .foregroundStyle(CallowayColors.textPrimary)
                }

                // Assistant Summary Card
                if let items = viewModel.briefing?.summaryItems {
                    AssistantSummaryCard(
                        summaryItems: items,
                        totalChats: viewModel.briefing?.totalChats ?? 0,
                        onViewAllChats: onViewAllChats
                    )
                }

                // Today's Schedule
                VStack(alignment: .leading, spacing: CallowaySpacing.md) {
                    HStack {
                        Text("Today's Schedule")
                            .font(CallowayFonts.title)
                            .foregroundStyle(CallowayColors.textPrimary)

                        if !viewModel.events.isEmpty {
                            Text("\(viewModel.events.count) events")
                                .font(CallowayFonts.small)
                                .foregroundStyle(CallowayColors.textSecondary)
                                .padding(.horizontal, CallowaySpacing.sm)
                                .padding(.vertical, CallowaySpacing.xs)
                                .background(CallowayColors.pillBackground)
                                .clipShape(Capsule())
                        }
                    }

                    ForEach(viewModel.events) { event in
                        ScheduleEventCard(event: event)
                    }
                }
            }
            .padding(.horizontal, CallowaySpacing.lg)
            .padding(.top, CallowaySpacing.md)
            .padding(.bottom, CallowaySpacing.xxxl)
        }
        .background(CallowayColors.background)
        .refreshable {
            await viewModel.load()
        }
        .task {
            if viewModel.briefing == nil {
                await viewModel.load()
            }
        }
    }
}

#Preview("Dark") {
    BriefingView()
        .onAppear {
            // Ensure mock data loads for preview
        }
        .preferredColorScheme(.dark)
}

#Preview("Light") {
    BriefingView()
        .onAppear {
            // Ensure mock data loads for preview
        }
        .preferredColorScheme(.light)
}
