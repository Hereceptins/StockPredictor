import Foundation
import UserNotifications

/// 推送通知服务
final class NotificationService: NSObject, @unchecked Sendable {
    static let shared = NotificationService()

    private let center = UNUserNotificationCenter.current()

    override private init() {
        super.init()
        center.delegate = self
    }

    // MARK: - 权限

    func requestAuthorization() async -> Bool {
        do {
            return try await center.requestAuthorization(options: [.alert, .badge, .sound])
        } catch {
            print("[Notification] Auth failed: \(error)")
            return false
        }
    }

    // MARK: - 本地通知（离线可用）

    func schedulePredictionAlert(stock: StockItem, direction: String, confidence: Double) {
        let content = UNMutableNotificationContent()
        content.title = "预测信号"
        content.body = "\(stock.name)(\(stock.symbol))：AI分析\(direction == "up" ? "看好" : "看淡")，置信度\(Int(confidence * 100))%"
        content.sound = .default
        content.badge = 1
        content.userInfo = ["stockCode": stock.code]

        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 5, repeats: false)
        let request = UNNotificationRequest(
            identifier: "prediction-\(stock.code)",
            content: content,
            trigger: trigger
        )

        center.add(request)
    }

    func scheduleLimitUpAlert(stock: StockItem) {
        let content = UNMutableNotificationContent()
        content.title = "涨停提醒"
        content.body = "\(stock.name)(\(stock.symbol)) 触及涨停"
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "limitup-\(stock.code)",
            content: content,
            trigger: nil
        )

        center.add(request)
    }

    func scheduleRiskAlert(message: String) {
        let content = UNMutableNotificationContent()
        content.title = "风险提醒"
        content.body = message
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "risk-\(Date().timeIntervalSince1970)",
            content: content,
            trigger: nil
        )

        center.add(request)
    }

    // MARK: - 清除

    func clearAll() {
        center.removeAllPendingNotificationRequests()
        center.removeAllDeliveredNotifications()
    }
}

// MARK: - UNUserNotificationCenterDelegate

extension NotificationService: UNUserNotificationCenterDelegate {
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .badge, .sound])
    }
}
