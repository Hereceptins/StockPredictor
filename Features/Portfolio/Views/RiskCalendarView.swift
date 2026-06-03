import SwiftUI

/// 风险日历 —— 未来一周宏观事件 + 个股事件
struct RiskCalendarView: View {
    @StateObject private var vm = RiskCalendarViewModel()

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // 未来一周风险事件
            Text("风险日历")
                .font(.headline)
                .padding(.horizontal)

            // 日期滚动
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(vm.nextWeekDays, id: \.self) { day in
                        DateCard(date: day, events: vm.eventsForDate(day))
                    }
                }
                .padding(.horizontal)
            }

            // 事件列表
            VStack(spacing: 10) {
                ForEach(vm.upcomingEvents) { event in
                    RiskEventRow(event: event)
                }
            }
            .padding(.horizontal)

            // 今日关注
            if !vm.todayAlerts.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("今日关注")
                        .font(.subheadline.bold())
                        .foregroundStyle(.orange)

                    ForEach(vm.todayAlerts) { alert in
                        AlertRow(alert: alert)
                    }
                }
                .padding()
                .background(Color.orange.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .padding(.horizontal)
            }
        }
        .padding(.vertical)
    }
}

// MARK: - 日期卡片

struct DateCard: View {
    let date: Date
    let events: [RiskEvent]

    var body: some View {
        VStack(spacing: 4) {
            Text(weekdayString)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            Text(dayString)
                .font(.title3.bold())
            if !events.isEmpty {
                Circle()
                    .fill(eventColor)
                    .frame(width: 6, height: 6)
            }
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 12)
        .background(isToday ? Color.orange.opacity(0.1) : Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isToday ? Color.orange : Color.clear, lineWidth: 1.5)
        )
        .shadow(color: .black.opacity(0.03), radius: 2)
    }

    private var isToday: Bool { Calendar.current.isDateInToday(date) }
    private var dayString: String { String(Calendar.current.component(.day, from: date)) }
    private var weekdayString: String {
        let f = DateFormatter(); f.dateFormat = "EEE"; return f.string(from: date)
    }

    private var eventColor: Color {
        let types = events.map(\.type)
        if types.contains(.macroEvent) { return .red }
        if types.contains(.unlock) { return .orange }
        if types.contains(.earnings) { return .blue }
        return .gray
    }
}

// MARK: - 风险事件行

struct RiskEventRow: View {
    let event: RiskEvent

    var body: some View {
        HStack(spacing: 12) {
            // 类型图标
            ZStack {
                Circle()
                    .fill(eventColor.opacity(0.12))
                    .frame(width: 32, height: 32)
                Image(systemName: eventIcon)
                    .font(.system(size: 13))
                    .foregroundStyle(eventColor)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(event.title)
                    .font(.subheadline)
                HStack(spacing: 6) {
                    Text(event.dateStr)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let stock = event.relatedStock {
                        Text(stock)
                            .font(.caption)
                            .padding(.horizontal, 4)
                            .background(Color(.systemGray6))
                            .clipShape(RoundedRectangle(cornerRadius: 2))
                    }
                    BadgeLabel(event.impact)
                }
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }

    private var eventColor: Color {
        switch event.type {
        case .macroEvent: return .red
        case .unlock: return .orange
        case .earnings: return .blue
        case .policy: return .purple
        case .dividend: return .green
        }
    }

    private var eventIcon: String {
        switch event.type {
        case .macroEvent: return "globe.asia.australia"
        case .unlock: return "lock.open"
        case .earnings: return "doc.text"
        case .policy: return "building.2"
        case .dividend: return "dollarsign.circle"
        }
    }
}

struct BadgeLabel: View {
    let text: String

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        Text(text)
            .font(.system(size: 9))
            .padding(.horizontal, 4)
            .padding(.vertical, 1)
            .background(
                text.contains("高") ? Color.red.opacity(0.12) :
                text.contains("中") ? Color.orange.opacity(0.12) :
                Color.green.opacity(0.12)
            )
            .foregroundStyle(
                text.contains("高") ? .red :
                text.contains("中") ? .orange : .green
            )
            .clipShape(Capsule())
    }
}

// MARK: - 今日提醒

struct AlertRow: View {
    let alert: RiskAlertItem

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: alert.icon)
                .font(.callout)
                .foregroundStyle(alert.severity == .high ? .red : .orange)

            VStack(alignment: .leading, spacing: 1) {
                Text(alert.message)
                    .font(.subheadline)
                if let detail = alert.detail {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()
        }
        .padding(.vertical, 2)
    }
}

struct RiskAlertItem: Identifiable {
    let id = UUID()
    let message: String
    let detail: String?
    let severity: Severity
    let icon: String

    enum Severity { case high, medium }
}

// MARK: - 数据模型

struct RiskEvent: Identifiable {
    let id = UUID()
    let date: Date
    let title: String
    let type: EventType
    let impact: String  // "高" / "中" / "低"
    let relatedStock: String?

    var dateStr: String {
        let f = DateFormatter(); f.dateFormat = "MM/dd"; return f.string(from: date)
    }

    enum EventType {
        case macroEvent   // 宏观事件（CPI/PMI/美联储）
        case unlock       // 限售股解禁
        case earnings     // 业绩预告
        case policy       // 政策事件
        case dividend     // 分红除权
    }
}

// MARK: - ViewModel

@MainActor
final class RiskCalendarViewModel: ObservableObject {
    @Published var upcomingEvents: [RiskEvent] = []
    @Published var todayAlerts: [RiskAlertItem] = []

    var nextWeekDays: [Date] {
        let calendar = Calendar.current
        let today = Date()
        return (0..<7).compactMap { calendar.date(byAdding: .day, value: $0, to: today) }
    }

    func eventsForDate(_ date: Date) -> [RiskEvent] {
        upcomingEvents.filter { Calendar.current.isDate($0.date, inSameDayAs: date) }
    }

    init() {
        loadMockData()
    }

    private func loadMockData() {
        let today = Date()
        let calendar = Calendar.current

        upcomingEvents = [
            RiskEvent(date: today, title: "CPI数据公布", type: .macroEvent, impact: "高", relatedStock: nil),
            RiskEvent(date: today, title: "宁德时代限售股解禁", type: .unlock, impact: "中", relatedStock: "300750"),
            RiskEvent(date: calendar.date(byAdding: .day, value: 1, to: today)!, title: "PMI数据公布", type: .macroEvent, impact: "高", relatedStock: nil),
            RiskEvent(date: calendar.date(byAdding: .day, value: 2, to: today)!, title: "贵州茅台业绩预告", type: .earnings, impact: "中", relatedStock: "600519"),
            RiskEvent(date: calendar.date(byAdding: .day, value: 2, to: today)!, title: "央行LPR报价", type: .policy, impact: "高", relatedStock: nil),
            RiskEvent(date: calendar.date(byAdding: .day, value: 3, to: today)!, title: "招商银行分红除权", type: .dividend, impact: "低", relatedStock: "600036"),
            RiskEvent(date: calendar.date(byAdding: .day, value: 4, to: today)!, title: "美联储议息会议", type: .macroEvent, impact: "高", relatedStock: nil),
            RiskEvent(date: calendar.date(byAdding: .day, value: 5, to: today)!, title: "比亚迪限售股解禁", type: .unlock, impact: "中", relatedStock: "002594"),
        ]

        todayAlerts = [
            RiskAlertItem(message: "CPI数据今日公布，预计同比+0.3%", detail: "可能影响消费板块", severity: .high, icon: "chart.line.uptrend.xyaxis"),
            RiskAlertItem(message: "宁德时代2000万股解禁", detail: "解禁市值约3.8亿元", severity: .medium, icon: "lock.open"),
        ]
    }
}

#Preview {
    ScrollView {
        RiskCalendarView()
    }
}
