import SwiftUI

/// 设置页面
struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @AppStorage("useLocalML") private var useLocalML = true
    @AppStorage("dataProvider") private var dataProvider = "baostock"
    @State private var showDisclaimer = false
    @State private var showLicense = false

    var body: some View {
        NavigationStack {
            Form {
                // MARK: AI模型
                Section {
                    Toggle("本地CoreML推理", isOn: $useLocalML)
                        .onChange(of: useLocalML) { _, val in
                            appState.isOffline = val
                        }

                    HStack {
                        Text("模型版本")
                        Spacer()
                        Text(appState.modelVersion)
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("最后同步")
                        Spacer()
                        Text(appState.lastSyncDate?.formatted() ?? "从未")
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("AI模型")
                }

                // MARK: 数据源
                Section {
                    Picker("数据源", selection: $dataProvider) {
                        Text("Baostock (免费)").tag("baostock")
                        Text("Tushare Pro").tag("tushare")
                    }

                    HStack {
                        Text("数据延迟")
                        Spacer()
                        Text(dataProvider == "baostock" ? "约15分钟" : "约3秒")
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("数据源")
                }

                // MARK: 推送通知
                Section {
                    Toggle("预测信号推送", isOn: .constant(false))
                    Toggle("涨跌停提醒", isOn: .constant(false))
                } header: {
                    Text("推送通知")
                }

                // MARK: 风险提示
                Section {
                    Button {
                        showDisclaimer = true
                    } label: {
                        Label("风险提示", systemImage: "exclamationmark.shield")
                    }
                    .sheet(isPresented: $showDisclaimer) {
                        DisclaimerView(isPresented: $showDisclaimer)
                    }

                    Button {
                        showLicense = true
                    } label: {
                        Label("法律声明", systemImage: "doc.text")
                    }
                    .sheet(isPresented: $showLicense) {
                        LicenseView()
                    }
                } header: {
                    Text("合规")
                }

                // MARK: 关于
                Section {
                    HStack {
                        Text("版本")
                        Spacer()
                        Text("1.0.0 (Beta)")
                            .foregroundStyle(.secondary)
                    }

                    Link(destination: URL(string: "https://tushare.pro")!) {
                        Label("Tushare数据来源", systemImage: "link")
                    }
                } header: {
                    Text("关于")
                }

                // 底部免责
                Section {
                    Text("本应用为AI辅助数据分析工具，所有预测结果仅供参考，不构成任何投资建议。股市有风险，投资需谨慎。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                }
            }
            .navigationTitle("设置")
        }
    }
}

// MARK: - 法律声明

struct LicenseView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("法律声明与免责条款")
                        .font(.title2.bold())

                    Text("""
                    1. 本应用（"智选K线"）是一款基于人工智能算法的A股数据分析工具，旨在为用户提供市场数据可视化、技术指标展示及基于历史数据的统计趋势分析。

                    2. 本应用不提供投资顾问服务。所有基于机器学习模型生成的"预测"、"评分"、"信号"均属于统计数据分析范畴，不构成任何形式的投资建议、荐股或买卖决策依据。

                    3. 本应用不承诺、不保证任何投资收益。历史数据表现不代表未来结果。AI模型基于历史数据训练的统计规律无法预测突发事件、政策变动、市场操纵等不可预见因素。

                    4. 用户使用本应用做出的任何投资决策，均由用户自行承担全部风险和责任。应用开发者不对用户的投资盈亏承担任何责任。

                    5. 本应用的数据来源于公开市场数据接口，可能存在数据延迟、缺失或不准确的情况。用户应以交易所实时行情为准。

                    6. 根据《金融产品网络营销管理办法》（2026年9月30日生效），本应用明确声明：不提供互动式投资咨询服务，不输出具体买卖时机建议，不使用"高收益""低风险""保证收益"等诱导性措辞。

                    7. 用户使用本应用即视为已阅读、理解并同意本声明全部条款。
                    """)
                    .font(.body)
                }
                .padding()
            }
            .navigationTitle("法律声明")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("关闭") { dismiss() }
                }
            }
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(AppState())
}
