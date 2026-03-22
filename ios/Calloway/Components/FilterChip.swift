import SwiftUI

struct FilterChip: View {
    let label: String
    let isSelected: Bool
    var iconName: String? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: CallowaySpacing.xs) {
                if let iconName = iconName {
                    Image(systemName: iconName)
                        .font(.system(size: 12))
                }
                Text(label)
                    .font(CallowayFonts.captionBold)
            }
            .padding(.horizontal, CallowaySpacing.md)
            .padding(.vertical, CallowaySpacing.sm)
            .background(isSelected ? CallowayColors.primaryAccent : Color.clear)
            .foregroundStyle(isSelected ? .white : CallowayColors.textSecondary)
            .clipShape(Capsule())
            .overlay(
                Capsule()
                    .stroke(
                        isSelected ? Color.clear : CallowayColors.cardBorder,
                        lineWidth: 1
                    )
            )
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    HStack(spacing: 8) {
        FilterChip(label: "All Chats", isSelected: true) {}
        FilterChip(label: "Unread", isSelected: false) {}
        FilterChip(label: "Bot Handled", isSelected: false, iconName: "cpu") {}
    }
    .padding()
    .background(CallowayColors.background)
}
