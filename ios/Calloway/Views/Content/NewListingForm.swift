import SwiftUI

struct NewListingForm: View {
    @Binding var address: String
    @Binding var price: String
    @Binding var beds: String
    @Binding var baths: String
    @Binding var description: String
    var onSubmit: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: CallowaySpacing.xl) {
            // Property Details section
            VStack(alignment: .leading, spacing: CallowaySpacing.lg) {
                Text("Property Details")
                    .font(CallowayFonts.headline)
                    .foregroundStyle(CallowayColors.textPrimary)

                // Address
                FormField(label: "ADDRESS", text: $address, placeholder: "Enter property address")

                // Price + Beds/Baths row
                HStack(spacing: CallowaySpacing.md) {
                    FormField(label: "PRICE", text: $price, placeholder: "$0", keyboard: .decimalPad)

                    HStack(spacing: CallowaySpacing.md) {
                        FormField(label: "BEDS", text: $beds, placeholder: "0", keyboard: .numberPad)
                        FormField(label: "BATHS", text: $baths, placeholder: "0", keyboard: .numberPad)
                    }
                }

                // Description
                VStack(alignment: .leading, spacing: CallowaySpacing.xs) {
                    Text("DESCRIPTION")
                        .font(CallowayFonts.label)
                        .foregroundStyle(CallowayColors.textTertiary)
                        .tracking(0.8)

                    TextEditor(text: $description)
                        .font(CallowayFonts.body)
                        .foregroundStyle(CallowayColors.textPrimary)
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 100)
                        .padding(CallowaySpacing.md)
                        .background(CallowayColors.inputBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(CallowayColors.cardBorder, lineWidth: 1)
                        )
                }
            }
            .padding(CallowaySpacing.lg)
            .cardStyle()

            // Upload Media section
            VStack(alignment: .leading, spacing: CallowaySpacing.md) {
                Text("Upload Media")
                    .font(CallowayFonts.headline)
                    .foregroundStyle(CallowayColors.textPrimary)

                Button {
                    // Media upload action
                } label: {
                    VStack(spacing: CallowaySpacing.sm) {
                        Image(systemName: "photo.badge.plus")
                            .font(.system(size: 28))
                            .foregroundStyle(CallowayColors.textTertiary)
                        Text("Tap to add photos or videos")
                            .font(CallowayFonts.caption)
                            .foregroundStyle(CallowayColors.textTertiary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, CallowaySpacing.xxl)
                    .background(CallowayColors.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(CallowayColors.cardBorder, style: StrokeStyle(lineWidth: 1, dash: [8]))
                    )
                }
                .buttonStyle(.plain)
            }

            // Submit button
            Button(action: onSubmit) {
                Text("Create Listing")
                    .font(CallowayFonts.headline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, CallowaySpacing.md)
                    .background(CallowayColors.primaryAccent)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - Form Field Component

private struct FormField: View {
    let label: String
    @Binding var text: String
    var placeholder: String = ""
    var keyboard: UIKeyboardType = .default

    var body: some View {
        VStack(alignment: .leading, spacing: CallowaySpacing.xs) {
            Text(label)
                .font(CallowayFonts.label)
                .foregroundStyle(CallowayColors.textTertiary)
                .tracking(0.8)

            TextField(placeholder, text: $text)
                .font(CallowayFonts.body)
                .foregroundStyle(CallowayColors.textPrimary)
                .keyboardType(keyboard)
                .padding(CallowaySpacing.md)
                .background(CallowayColors.inputBackground)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(CallowayColors.cardBorder, lineWidth: 1)
                )
        }
    }
}

#Preview("Dark") {
    ScrollView {
        NewListingForm(
            address: .constant(""),
            price: .constant(""),
            beds: .constant(""),
            baths: .constant(""),
            description: .constant(""),
            onSubmit: {}
        )
        .padding()
    }
    .background(CallowayColors.background)
    .preferredColorScheme(.dark)
}

#Preview("Light") {
    ScrollView {
        NewListingForm(
            address: .constant(""),
            price: .constant(""),
            beds: .constant(""),
            baths: .constant(""),
            description: .constant(""),
            onSubmit: {}
        )
        .padding()
    }
    .background(CallowayColors.background)
    .preferredColorScheme(.light)
}
