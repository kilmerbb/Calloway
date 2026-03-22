import SwiftUI

// MARK: - Colors

enum CallowayColors {
    static let background = Color(hex: 0x000000)
    static let cardBackground = Color(hex: 0x1C1C1E)
    static let cardBorder = Color(hex: 0x333333)
    static let primaryAccent = Color(hex: 0x7C3AED)
    static let primaryAccentLight = Color(hex: 0x9B6DFF)
    static let gradientStart = Color(hex: 0x7C3AED)
    static let gradientEnd = Color(hex: 0x4F46E5)
    static let textPrimary = Color.white
    static let textSecondary = Color(hex: 0x9CA3AF)
    static let textTertiary = Color(hex: 0x6B7280)
    static let amber = Color(hex: 0xF59E0B)
    static let amberBackground = Color(hex: 0x78350F).opacity(0.6)
    static let green = Color(hex: 0x22C55E)
    static let tabBarBackground = Color(hex: 0x111111)
    static let inputBackground = Color(hex: 0x1C1C1E)
    static let pillBackground = Color(hex: 0x2A2A2E)
    static let segmentActive = Color.white
    static let segmentInactive = Color.clear

    static var purpleGradient: LinearGradient {
        LinearGradient(
            colors: [gradientStart, gradientEnd],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

// MARK: - Fonts

enum CallowayFonts {
    static let largeTitle = Font.system(size: 28, weight: .bold)
    static let title = Font.system(size: 22, weight: .bold)
    static let headline = Font.system(size: 17, weight: .semibold)
    static let subheadline = Font.system(size: 15, weight: .medium)
    static let body = Font.system(size: 15, weight: .regular)
    static let caption = Font.system(size: 13, weight: .regular)
    static let captionBold = Font.system(size: 13, weight: .semibold)
    static let small = Font.system(size: 11, weight: .medium)
    static let label = Font.system(size: 12, weight: .bold)
}

// MARK: - Spacing

enum CallowaySpacing {
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let lg: CGFloat = 16
    static let xl: CGFloat = 20
    static let xxl: CGFloat = 24
    static let xxxl: CGFloat = 32
}

// MARK: - Color Hex Extension

extension Color {
    init(hex: UInt, alpha: Double = 1.0) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0,
            opacity: alpha
        )
    }
}

// MARK: - View Modifiers

struct CardStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(CallowayColors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(CallowayColors.cardBorder, lineWidth: 1)
            )
    }
}

extension View {
    func cardStyle() -> some View {
        modifier(CardStyle())
    }
}
