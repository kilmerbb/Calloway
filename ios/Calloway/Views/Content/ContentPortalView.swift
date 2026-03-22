import SwiftUI

@Observable
final class ContentPortalViewModel {
    var listings: [Listing] = []
    var selectedTab: ContentTab = .newListing
    var isLoading = false
    var isSubmitting = false
    var error: String?

    // Form fields
    var address = ""
    var price = ""
    var beds = ""
    var baths = ""
    var description = ""

    private let apiClient = APIClient.shared

    func loadListings() async {
        isLoading = true
        do {
            listings = try await apiClient.get("/api/mobile/listings")
        } catch {
            listings = Listing.mockListings
        }
        isLoading = false
    }

    func createListing() async {
        guard !address.isEmpty else { return }

        isSubmitting = true
        let request = CreateListingRequest(
            address: address,
            price: Double(price) ?? 0,
            beds: Int(beds) ?? 0,
            baths: Double(baths) ?? 0,
            description: description
        )

        do {
            let newListing: Listing = try await apiClient.post(
                "/api/mobile/listings",
                body: request
            )
            listings.insert(newListing, at: 0)
            clearForm()
            selectedTab = .myContent
        } catch {
            self.error = "Failed to create listing"
        }

        isSubmitting = false
    }

    func clearForm() {
        address = ""
        price = ""
        beds = ""
        baths = ""
        description = ""
    }
}

struct ContentPortalView: View {
    @State private var viewModel = ContentPortalViewModel()

    var body: some View {
        VStack(spacing: 0) {
            // Header
            VStack(alignment: .leading, spacing: CallowaySpacing.lg) {
                Text("Content Portal")
                    .font(CallowayFonts.largeTitle)
                    .foregroundStyle(CallowayColors.textPrimary)
                    .padding(.horizontal, CallowaySpacing.lg)

                // Segmented control
                HStack(spacing: 0) {
                    ForEach(ContentTab.allCases, id: \.self) { tab in
                        Button {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                viewModel.selectedTab = tab
                            }
                        } label: {
                            Text(tab.rawValue)
                                .font(CallowayFonts.captionBold)
                                .foregroundStyle(
                                    viewModel.selectedTab == tab
                                        ? CallowayColors.background
                                        : CallowayColors.textSecondary
                                )
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, CallowaySpacing.sm)
                                .background(
                                    viewModel.selectedTab == tab
                                        ? CallowayColors.segmentActive
                                        : CallowayColors.segmentInactive
                                )
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(3)
                .background(CallowayColors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .padding(.horizontal, CallowaySpacing.lg)
            }
            .padding(.top, CallowaySpacing.md)
            .padding(.bottom, CallowaySpacing.lg)

            // Content
            ScrollView {
                switch viewModel.selectedTab {
                case .newListing:
                    NewListingForm(
                        address: $viewModel.address,
                        price: $viewModel.price,
                        beds: $viewModel.beds,
                        baths: $viewModel.baths,
                        description: $viewModel.description,
                        onSubmit: {
                            Task {
                                await viewModel.createListing()
                            }
                        }
                    )
                    .padding(.horizontal, CallowaySpacing.lg)

                case .myContent:
                    if viewModel.listings.isEmpty && !viewModel.isLoading {
                        VStack(spacing: CallowaySpacing.md) {
                            Image(systemName: "doc.text")
                                .font(.system(size: 40))
                                .foregroundStyle(CallowayColors.textTertiary)
                            Text("No listings yet")
                                .font(CallowayFonts.body)
                                .foregroundStyle(CallowayColors.textSecondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.top, 80)
                    } else {
                        LazyVStack(spacing: CallowaySpacing.md) {
                            ForEach(viewModel.listings) { listing in
                                ListingCard(listing: listing)
                            }
                        }
                        .padding(.horizontal, CallowaySpacing.lg)
                    }
                }
            }
            .padding(.bottom, CallowaySpacing.xxxl)
        }
        .background(CallowayColors.background)
        .task {
            if viewModel.listings.isEmpty {
                await viewModel.loadListings()
            }
        }
    }
}

// MARK: - Listing Card

private struct ListingCard: View {
    let listing: Listing

    private var formattedPrice: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: listing.price)) ?? "$\(Int(listing.price))"
    }

    private var bathsFormatted: String {
        listing.baths.truncatingRemainder(dividingBy: 1) == 0
            ? "\(Int(listing.baths))"
            : String(format: "%.1f", listing.baths)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: CallowaySpacing.md) {
            HStack {
                VStack(alignment: .leading, spacing: CallowaySpacing.xs) {
                    Text(listing.address)
                        .font(CallowayFonts.headline)
                        .foregroundStyle(CallowayColors.textPrimary)
                    Text(formattedPrice)
                        .font(CallowayFonts.subheadline)
                        .foregroundStyle(CallowayColors.primaryAccent)
                }

                Spacer()

                Text(listing.status.rawValue.capitalized)
                    .font(CallowayFonts.small)
                    .foregroundStyle(statusColor)
                    .padding(.horizontal, CallowaySpacing.sm)
                    .padding(.vertical, CallowaySpacing.xs)
                    .background(statusColor.opacity(0.15))
                    .clipShape(Capsule())
            }

            HStack(spacing: CallowaySpacing.lg) {
                Label("\(listing.beds) beds", systemImage: "bed.double")
                Label("\(bathsFormatted) baths", systemImage: "shower")
            }
            .font(CallowayFonts.caption)
            .foregroundStyle(CallowayColors.textSecondary)

            if !listing.description.isEmpty {
                Text(listing.description)
                    .font(CallowayFonts.caption)
                    .foregroundStyle(CallowayColors.textSecondary)
                    .lineLimit(2)
            }
        }
        .padding(CallowaySpacing.lg)
        .cardStyle()
    }

    private var statusColor: Color {
        switch listing.status {
        case .active: return CallowayColors.green
        case .draft: return CallowayColors.textTertiary
        case .pending: return CallowayColors.amber
        case .sold: return CallowayColors.primaryAccent
        }
    }
}

#Preview("Dark") {
    ContentPortalView()
        .preferredColorScheme(.dark)
}

#Preview("Light") {
    ContentPortalView()
        .preferredColorScheme(.light)
}
