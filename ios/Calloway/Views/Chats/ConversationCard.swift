import SwiftUI

struct ConversationCard: View {
    let conversation: ConversationListItem

    var body: some View {
        HStack(spacing: CallowaySpacing.md) {
            // Avatar
            AvatarView(
                initials: conversation.contactInitials,
                colorHex: conversation.avatarColor,
                size: 48,
                isOnline: conversation.isOnline
            )

            // Content
            VStack(alignment: .leading, spacing: CallowaySpacing.xs) {
                // Name + timestamp row
                HStack {
                    Text(conversation.contactName)
                        .font(CallowayFonts.headline)
                        .foregroundStyle(CallowayColors.textPrimary)
                    Spacer()
                    Text(conversation.lastMessageAt.relativeTimestamp())
                        .font(CallowayFonts.caption)
                        .foregroundStyle(CallowayColors.textTertiary)
                }

                // Message preview
                HStack(spacing: CallowaySpacing.xs) {
                    if conversation.isBotHandled {
                        Image(systemName: "cpu")
                            .font(.system(size: 11))
                            .foregroundStyle(CallowayColors.textTertiary)
                    }
                    Text(conversation.lastMessagePreview)
                        .font(CallowayFonts.body)
                        .foregroundStyle(CallowayColors.textSecondary)
                        .lineLimit(1)
                }
            }

            // Unread badge
            if conversation.unreadCount > 0 {
                Text("\(conversation.unreadCount)")
                    .font(CallowayFonts.small)
                    .foregroundStyle(.white)
                    .frame(width: 22, height: 22)
                    .background(CallowayColors.primaryAccent)
                    .clipShape(Circle())
            }
        }
        .padding(CallowaySpacing.md)
        .contentShape(Rectangle())
    }
}

#Preview {
    VStack(spacing: 0) {
        ForEach(ConversationListItem.mockConversations) { conversation in
            ConversationCard(conversation: conversation)
            if conversation.id != ConversationListItem.mockConversations.last?.id {
                Divider()
                    .background(CallowayColors.cardBorder)
                    .padding(.leading, 76)
            }
        }
    }
    .background(CallowayColors.background)
}
