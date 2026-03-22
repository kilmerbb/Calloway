import SwiftUI

struct AssistantSummaryCard: View {
    let summaryItems: [String]
    let totalChats: Int
    var onViewAllChats: (() -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: CallowaySpacing.lg) {
            // Header
            HStack {
                Image(systemName: "calendar")
                    .font(.system(size: 16))
                Text("Assistant Summary")
                    .font(CallowayFonts.headline)
                Spacer()
                Image(systemName: "sparkles")
                    .font(.system(size: 16))
            }
            .foregroundStyle(.white)

            // Bullet list
            VStack(alignment: .leading, spacing: CallowaySpacing.sm) {
                ForEach(summaryItems, id: \.self) { item in
                    HStack(alignment: .top, spacing: CallowaySpacing.sm) {
                        Text("\u{2022}")
                            .font(CallowayFonts.body)
                        Text(item)
                            .font(CallowayFonts.body)
                    }
                    .foregroundStyle(.white.opacity(0.9))
                }
            }

            // View All Chats button
            Button(action: { onViewAllChats?() }) {
                Text("View All Chats")
                    .font(CallowayFonts.captionBold)
                    .foregroundStyle(.white)
                    .padding(.horizontal, CallowaySpacing.lg)
                    .padding(.vertical, CallowaySpacing.sm)
                    .background(.white.opacity(0.2))
                    .clipShape(Capsule())
            }
            .buttonStyle(.plain)
        }
        .padding(CallowaySpacing.xl)
        .background(CallowayColors.purpleGradient)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

#Preview {
    AssistantSummaryCard(
        summaryItems: [
            "Responded to 3 new leads overnight",
            "Confirmed showing with Sarah Jenkins at 10 AM",
            "Sent follow-up to Mike Thompson about appraisal",
            "Scheduled open house reminder for Sunday"
        ],
        totalChats: 12
    )
    .padding()
    .background(CallowayColors.background)
}
