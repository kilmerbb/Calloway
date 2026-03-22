import SwiftUI

// MARK: - Colors

enum CallowayColors {
    // MARK: - Adaptive Colors (Dark / Light)

    static let background = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 0, green: 0, blue: 0, alpha: 1)                         // #000000
            : UIColor(red: 0.973, green: 0.976, blue: 0.980, alpha: 1)             // #F8F9FA
    })

    static let cardBackground = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 0.110, green: 0.110, blue: 0.118, alpha: 1)             // #1C1C1E
            : UIColor(red: 1, green: 1, blue: 1, alpha: 1)                         // #FFFFFF
    })

    static let cardBorder = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 0.2, green: 0.2, blue: 0.2, alpha: 1)                   // #333333
            : UIColor(red: 0.898, green: 0.906, blue: 0.922, alpha: 1)             // #E5E7EB
    })

    static let primaryAccent = Color(hex: 0x7C3AED)
    static let primaryAccentLight = Color(hex: 0x9B6DFF)

    static let gradientStart = Color(hex: 0x7C3AED)
    static let gradientEnd = Color(hex: 0x4F46E5)

    static let textPrimary = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 1, green: 1, blue: 1, alpha: 1)                         // white
            : UIColor(red: 0.067, green: 0.094, blue: 0.153, alpha: 1)             // #111827
    })

    static let textSecondary = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 0.612, green: 0.639, blue: 0.686, alpha: 1)             // #9CA3AF
            : UIColor(red: 0.420, green: 0.447, blue: 0.498, alpha: 1)             // #6B7280
    })

    static let textTertiary = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 0.420, green: 0.447, blue: 0.498, alpha: 1)             // #6B7280
            : UIColor(red: 0.612, green: 0.639, blue: 0.686, alpha: 1)             // #9CA3AF
    })

    static let amber = Color(hex: 0xF59E0B)

    static let amberBackground = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 0.471, green: 0.208, blue: 0.059, alpha: 0.6)           // #78350F @ 0.6
            : UIColor(red: 0.996, green: 0.953, blue: 0.780, alpha: 1.0)           // #FEF3C7
    })

    static let green = Color(hex: 0x22C55E)

    static let tabBarBackground = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 0.067, green: 0.067, blue: 0.067, alpha: 1)             // #111111
            : UIColor(red: 1, green: 1, blue: 1, alpha: 1)                         // #FFFFFF
    })

    static let inputBackground = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 0.110, green: 0.110, blue: 0.118, alpha: 1)             // #1C1C1E
            : UIColor(red: 0.953, green: 0.957, blue: 0.965, alpha: 1)             // #F3F4F6
    })

    static let pillBackground = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 0.165, green: 0.165, blue: 0.180, alpha: 1)             // #2A2A2E
            : UIColor(red: 0.898, green: 0.906, blue: 0.922, alpha: 1)             // #E5E7EB
    })

    static let segmentActive = Color(UIColor { traitCollection in
        traitCollection.userInterfaceStyle == .dark
            ? UIColor(red: 1, green: 1, blue: 1, alpha: 1)                         // white
            : UIColor(red: 0.067, green: 0.094, blue: 0.153, alpha: 1)             // #111827
    })

    static let segmentInactive = Color.clear

    // MARK: - Gradients

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
