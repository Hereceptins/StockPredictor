import SwiftUI

/// AI预测卡片 —— 每日精选池的核心展示组件
struct PredictionCardView: View {
    let stock: StockItem
    @State private var prediction: PredictionRecord?
    @State private var multiFactorScore: MultiFactorScore?

    var body: some View {
        VStack(spacing: 0) {
            // 顶部：股票信息 + 方向指示
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(stock.name)
                        .font(.headline)
                    Text(stock.symbol)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                if let pred = prediction {
                    DirectionBadge(direction: pred.direction, confidence: pred.confidence)
                } else {
                    ProgressView()
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 14)

            Divider().padding(.vertical, 10)

            // 信号标签
            if let tags = prediction?.signalTags, !tags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(tags, id: \.self) { tag in
                            TagView(label: tag)
                        }
                    }
                    .padding(.horizontal, 16)
                }
                .padding(.bottom, 8)
            }

            // 多因子评分
            if let score = multiFactorScore {
                MultiFactorBar(score: score)
                    .padding(.horizontal, 16)
                    .padding(.bottom, 12)
            }

            // 免责声明
            Text("AI预测仅供参考，不构成投资建议")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.bottom, 8)
        }
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .shadow(color: .black.opacity(0.06), radius: 6, y: 2)
        .onAppear { loadPrediction() }
    }

    private func loadPrediction() {
        // TODO: 从本地SwiftData或后端API加载最新预测
    }
}

// MARK: - 方向指示徽章

struct DirectionBadge: View {
    let direction: String
    let confidence: Double

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: direction == "up" ? "arrow.up.circle.fill" : "arrow.down.circle.fill")
                .font(.title2)
            VStack(alignment: .leading, spacing: 1) {
                Text(direction == "up" ? "看好" : "看淡")
                    .font(.subheadline.bold())
                Text("\(Int(confidence * 100))% 置信")
                    .font(.caption2)
            }
        }
        .foregroundStyle(direction == "up" ? .red : .green)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background((direction == "up" ? Color.red : Color.green).opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

// MARK: - 信号标签

struct TagView: View {
    let label: String

    var body: some View {
        Text(label)
            .font(.caption)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(tagColor.opacity(0.12))
            .foregroundStyle(tagColor)
            .clipShape(Capsule())
    }

    private var tagColor: Color {
        switch label {
        case "资金流入": return .blue
        case "政策催化": return .purple
        case "技术突破": return .orange
        case "情绪反转": return .pink
        default: return .gray
        }
    }
}

// MARK: - 多因子评分条

struct MultiFactorBar: View {
    let score: MultiFactorScore

    var body: some View {
        VStack(spacing: 6) {
            HStack {
                Text("综合评分")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(Int(score.overall))/100")
                    .font(.caption.bold())
                    .foregroundStyle(score.overall >= 70 ? .red : score.overall >= 40 ? .orange : .gray)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color(.systemGray5))
                        .frame(height: 8)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(score.overall >= 70 ? Color.red : score.overall >= 40 ? Color.orange : Color.gray)
                        .frame(width: geo.size.width * score.overall / 100, height: 8)
                }
            }
            .frame(height: 8)
        }
    }
}

// MARK: - 多因子评分模型

struct MultiFactorScore {
    let overall: Double       // 0-100
    let momentum: Double
    let value: Double
    let quality: Double
    let sentiment: Double
    let technical: Double
}

#Preview {
    ScrollView {
        PredictionCardView(stock: StockItem(code: "000001.SZ", name: "平安银行", market: "SZ"))
            .padding()
    }
}
