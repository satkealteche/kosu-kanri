"""
予実分析ツール - Streamlit App
Phase 1: CSV取込 + 月次推移表
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO
import sys
import os

# モジュールパスを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from budget_forecast.parser.yayoi import YayoiParser
from budget_forecast.analyzer.expense import ExpenseAnalyzer

# ページ設定
st.set_page_config(
    page_title="予実分析ツール",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# セッション状態の初期化
if 'df' not in st.session_state:
    st.session_state.df = None
if 'meta' not in st.session_state:
    st.session_state.meta = None
if 'monthly_summary' not in st.session_state:
    st.session_state.monthly_summary = None


def main():
    st.title("📊 予実分析ツール")
    st.markdown("弥生会計の仕訳データから月次推移表を作成し、予算管理を支援します。")

    # サイドバー：設定
    with st.sidebar:
        st.header("⚙️ 設定")

        fiscal_year_end = st.selectbox(
            "決算月",
            options=list(range(1, 13)),
            index=2,  # 3月
            format_func=lambda x: f"{x}月"
        )

        st.divider()

        st.header("📁 データ取込")
        uploaded_file = st.file_uploader(
            "仕訳帳CSV（弥生会計）",
            type=['csv'],
            help="弥生会計からエクスポートした仕訳日記帳CSVをアップロードしてください"
        )

        encoding = st.selectbox(
            "文字コード",
            options=['cp932', 'utf-8', 'shift_jis'],
            index=0,
            help="通常は'cp932'（Shift-JIS）です"
        )

        if uploaded_file is not None:
            if st.button("📥 データ読込", type="primary"):
                load_data(uploaded_file, encoding, fiscal_year_end)

    # メインコンテンツ
    if st.session_state.df is not None:
        display_dashboard()
    else:
        display_welcome()


def load_data(uploaded_file, encoding: str, fiscal_year_end: int):
    """CSVデータを読み込む"""
    try:
        with st.spinner("データを読み込んでいます..."):
            parser = YayoiParser(fiscal_year_end_month=fiscal_year_end)
            df, meta = parser.parse_csv(uploaded_file, encoding=encoding)

            st.session_state.df = df
            st.session_state.meta = meta
            st.session_state.fiscal_year_end = fiscal_year_end

            # 月次推移表を作成
            analyzer = ExpenseAnalyzer(fiscal_year_end_month=fiscal_year_end)
            expense_accounts = analyzer.get_expense_accounts()

            # 経費データをフィルタ（借方に経費科目があるもの）
            expense_df = df[df['借方勘定科目'].isin(expense_accounts)]
            st.session_state.expense_df = expense_df

            monthly_summary = analyzer.create_monthly_summary(
                expense_df,
                account_column='借方勘定科目',
                amount_column='借方金額'
            )
            st.session_state.monthly_summary = monthly_summary

            st.success(f"✅ {meta['total_records']:,}件の仕訳を読み込みました")
            st.rerun()

    except Exception as e:
        st.error(f"❌ 読込エラー: {str(e)}")
        st.exception(e)


def display_welcome():
    """初期画面"""
    st.info("👈 サイドバーからCSVファイルをアップロードしてください")

    with st.expander("📖 使い方", expanded=True):
        st.markdown("""
        ### 1. データの準備
        弥生会計から「仕訳日記帳」をCSV形式でエクスポートしてください。

        ### 2. ファイルのアップロード
        左のサイドバーからCSVファイルをアップロードします。

        ### 3. 分析
        - **月次推移表**: 勘定科目別の月次推移を確認
        - **グラフ**: 推移をビジュアルで確認
        - **エクスポート**: Excelでダウンロード
        """)


def display_dashboard():
    """メインダッシュボード"""
    df = st.session_state.df
    meta = st.session_state.meta

    # 概要
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("総仕訳数", f"{meta['total_records']:,}件")
    with col2:
        date_min = meta['date_range'][0].strftime('%Y/%m')
        st.metric("開始月", date_min)
    with col3:
        date_max = meta['date_range'][1].strftime('%Y/%m')
        st.metric("終了月", date_max)
    with col4:
        fy_list = ', '.join([f"FY{fy}" for fy in sorted(meta['fiscal_years'])])
        st.metric("会計年度", fy_list)

    st.divider()

    # タブ
    tab1, tab2, tab3, tab4 = st.tabs(["📋 月次推移表", "📈 グラフ", "🔍 明細", "💾 エクスポート"])

    with tab1:
        display_monthly_summary()

    with tab2:
        display_charts()

    with tab3:
        display_detail()

    with tab4:
        display_export()


def display_monthly_summary():
    """月次推移表を表示"""
    st.subheader("月次推移表（経費）")

    monthly_summary = st.session_state.monthly_summary

    if monthly_summary is None or monthly_summary.empty:
        st.warning("経費データがありません")
        return

    # フィルタ
    all_accounts = [acc for acc in monthly_summary.index if acc != '合計']
    selected_accounts = st.multiselect(
        "表示する勘定科目",
        options=all_accounts,
        default=all_accounts[:10] if len(all_accounts) > 10 else all_accounts
    )

    if not selected_accounts:
        st.warning("勘定科目を選択してください")
        return

    # フィルタ適用
    display_df = monthly_summary.loc[selected_accounts + ['合計']]

    # 数値フォーマット
    styled_df = display_df.style.format("{:,.0f}")

    st.dataframe(
        styled_df,
        use_container_width=True,
        height=400
    )

    # 合計の推移
    st.markdown("**月次合計の推移**")
    totals = monthly_summary.loc['合計']
    col1, col2 = st.columns([3, 1])
    with col1:
        fig = px.bar(
            x=[str(p) for p in totals.index],
            y=totals.values,
            labels={'x': '年月', 'y': '金額'},
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.metric("期間合計", f"¥{totals.sum():,.0f}")
        st.metric("月平均", f"¥{totals.mean():,.0f}")


def display_charts():
    """グラフ表示"""
    st.subheader("推移グラフ")

    monthly_summary = st.session_state.monthly_summary

    if monthly_summary is None or monthly_summary.empty:
        st.warning("データがありません")
        return

    # グラフタイプ選択
    chart_type = st.radio(
        "グラフタイプ",
        options=["積み上げ棒グラフ", "折れ線グラフ", "エリアチャート"],
        horizontal=True
    )

    # 勘定科目選択
    all_accounts = [acc for acc in monthly_summary.index if acc != '合計']
    selected = st.multiselect(
        "表示する勘定科目（最大10個推奨）",
        options=all_accounts,
        default=all_accounts[:5] if len(all_accounts) > 5 else all_accounts
    )

    if not selected:
        st.warning("勘定科目を選択してください")
        return

    # データ準備
    plot_df = monthly_summary.loc[selected].T
    plot_df.index = plot_df.index.astype(str)

    # グラフ描画
    if chart_type == "積み上げ棒グラフ":
        fig = px.bar(
            plot_df,
            barmode='stack',
            labels={'value': '金額', 'index': '年月'}
        )
    elif chart_type == "折れ線グラフ":
        fig = px.line(
            plot_df,
            markers=True,
            labels={'value': '金額', 'index': '年月'}
        )
    else:
        fig = px.area(
            plot_df,
            labels={'value': '金額', 'index': '年月'}
        )

    fig.update_layout(
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    st.plotly_chart(fig, use_container_width=True)


def display_detail():
    """明細表示"""
    st.subheader("仕訳明細")

    df = st.session_state.df

    # フィルタ
    col1, col2, col3 = st.columns(3)

    with col1:
        accounts = df['借方勘定科目'].dropna().unique().tolist()
        selected_account = st.selectbox(
            "勘定科目",
            options=['（すべて）'] + sorted(accounts)
        )

    with col2:
        fiscal_years = sorted(df['会計年度'].dropna().unique().tolist())
        selected_fy = st.selectbox(
            "会計年度",
            options=['（すべて）'] + [f'FY{fy}' for fy in fiscal_years]
        )

    with col3:
        search_text = st.text_input("摘要検索")

    # フィルタ適用
    filtered_df = df.copy()

    if selected_account != '（すべて）':
        filtered_df = filtered_df[filtered_df['借方勘定科目'] == selected_account]

    if selected_fy != '（すべて）':
        fy = int(selected_fy.replace('FY', ''))
        filtered_df = filtered_df[filtered_df['会計年度'] == fy]

    if search_text:
        filtered_df = filtered_df[
            filtered_df['摘要'].fillna('').str.contains(search_text, case=False)
        ]

    # 表示カラム
    display_cols = ['日付', '借方勘定科目', '借方補助科目', '借方金額', '摘要', '会計年度']
    display_cols = [c for c in display_cols if c in filtered_df.columns]

    st.dataframe(
        filtered_df[display_cols].sort_values('日付', ascending=False),
        use_container_width=True,
        height=400
    )

    st.caption(f"表示: {len(filtered_df):,}件 / 全{len(df):,}件")


def display_export():
    """エクスポート"""
    st.subheader("データエクスポート")

    monthly_summary = st.session_state.monthly_summary

    if monthly_summary is None:
        st.warning("データがありません")
        return

    # CSV出力
    st.markdown("### 📄 CSV形式")

    csv = monthly_summary.to_csv(encoding='utf-8-sig')
    st.download_button(
        label="📥 月次推移表をCSVでダウンロード",
        data=csv,
        file_name="monthly_summary.csv",
        mime="text/csv"
    )

    # Excel出力
    st.markdown("### 📊 Excel形式")

    from io import BytesIO

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        monthly_summary.to_excel(writer, sheet_name='月次推移表')

        # 仕訳明細も出力
        if st.session_state.expense_df is not None:
            expense_df = st.session_state.expense_df.copy()
            # Period型を文字列に変換
            if '年月' in expense_df.columns:
                expense_df['年月'] = expense_df['年月'].astype(str)
            expense_df.to_excel(writer, sheet_name='経費明細', index=False)

    st.download_button(
        label="📥 Excelでダウンロード",
        data=buffer.getvalue(),
        file_name="budget_analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == "__main__":
    main()
