import SwiftUI

struct MessageBubble: View {
    let message: Message

    private var isContact: Bool {
        message.sender == .contact
    }

    private var isAssistant: Bool {
        message.sender == .assistant
    }

    var body: some View {
        HStack {
            if isContact {
                Spacer(minLength: 60)
            }

            VStack(alignment: isContact ? .trailing : .leading, spacing: CallowaySpacing.xs) {
                if isAssistant {
                    Text("ASSISTANT")
                        .font(CallowayFonts.label)
                        .foregroundStyle(CallowayColors.primaryAccent)
                        .tracking(0.8)
                }

                Text(message.body)
                    .font(CallowayFonts.body)
                    .foregroundStyle(CallowayColors.textPrimary)
                    .padding(CallowaySpacing.md)
                    .background(bubbleBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .overlay(
                        Group {
                            if isAssistant {
                                RoundedRectangle(cornerRadius: 16)
                                    .stroke(CallowayColors.cardBorder, lineWidth: 1)
                            }
                        }
                    )

                Text(message.createdAt.relativeTimestamp())
                    .font(CallowayFonts.caption)
                    .foregroundStyle(CallowayColors.textTertiary)
            }

            if !isContact {
                Spacer(minLength: 60)
            }
        }
    }

    @ViewBuilder
    private var bubbleBackground: some View {
        if isContact {
            CallowayColors.primaryAccent
        } else {
            CallowayColors.cardBackground
        }
    }
}

#Preview {
    VStack(spacing: 16) {
        ForEach(Message.mockMessages) { message in
            MessageBubble(message: message)
        }
    }
    .padding()
    .background(CallowayColors.background)
}
