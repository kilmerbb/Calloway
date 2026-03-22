import SwiftUI

struct AvatarView: View {
    let initials: String
    let colorHex: String
    var size: CGFloat = 48
    var isOnline: Bool = false

    private var avatarColor: Color {
        colorFromHex(colorHex)
    }

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            Circle()
                .fill(avatarColor.opacity(0.3))
                .frame(width: size, height: size)
                .overlay(
                    Text(initials)
                        .font(.system(size: size * 0.35, weight: .semibold))
                        .foregroundStyle(avatarColor)
                )

            if isOnline {
                Circle()
                    .fill(CallowayColors.green)
                    .frame(width: size * 0.28, height: size * 0.28)
                    .overlay(
                        Circle()
                            .stroke(CallowayColors.background, lineWidth: 2)
                    )
                    .offset(x: 2, y: 2)
            }
        }
    }

    private func colorFromHex(_ hex: String) -> Color {
        let cleaned = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard let value = UInt(cleaned, radix: 16) else {
            return CallowayColors.primaryAccent
        }
        return Color(hex: value)
    }
}

#Preview {
    HStack(spacing: 16) {
        AvatarView(initials: "JD", colorHex: "#4F46E5", isOnline: true)
        AvatarView(initials: "SJ", colorHex: "#DC2626")
        AvatarView(initials: "MT", colorHex: "#059669", size: 36, isOnline: true)
        AvatarView(initials: "DR", colorHex: "#D97706", size: 56)
    }
    .padding()
    .background(CallowayColors.background)
}
