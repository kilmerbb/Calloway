import SwiftUI

struct ScheduleEventCard: View {
    let event: ScheduleEvent

    var body: some View {
        HStack(spacing: CallowaySpacing.md) {
            // Event details
            VStack(alignment: .leading, spacing: CallowaySpacing.sm) {
                // Time
                HStack(spacing: CallowaySpacing.xs) {
                    Image(systemName: "clock")
                        .font(.system(size: 13))
                        .foregroundStyle(CallowayColors.primaryAccent)
                    Text(event.time)
                        .font(CallowayFonts.caption)
                        .foregroundStyle(CallowayColors.primaryAccent)
                }

                // Event type
                Text(event.type)
                    .font(CallowayFonts.headline)
                    .foregroundStyle(CallowayColors.textPrimary)

                // Address
                HStack(spacing: CallowaySpacing.xs) {
                    Image(systemName: "mappin")
                        .font(.system(size: 12))
                        .foregroundStyle(CallowayColors.textSecondary)
                    Text(event.address)
                        .font(CallowayFonts.caption)
                        .foregroundStyle(CallowayColors.textSecondary)
                }

                // Contact
                HStack(spacing: CallowaySpacing.xs) {
                    Image(systemName: "calendar")
                        .font(.system(size: 12))
                        .foregroundStyle(CallowayColors.textSecondary)
                    Text(event.contactName)
                        .font(CallowayFonts.caption)
                        .foregroundStyle(CallowayColors.textSecondary)
                }
            }

            Spacer()

            // Chevron
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(CallowayColors.textTertiary)
        }
        .padding(CallowaySpacing.lg)
        .cardStyle()
    }
}

#Preview {
    VStack(spacing: 12) {
        ForEach(ScheduleEvent.mockEvents) { event in
            ScheduleEventCard(event: event)
        }
    }
    .padding()
    .background(CallowayColors.background)
}
