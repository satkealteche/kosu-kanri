"""
経費分析モジュール
- 月次推移表の作成
- スポット/継続の分類
- 予測ロジック
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ExpenseType(Enum):
    """経費タイプ"""
    RECURRING = "継続"
    SPOT = "スポット"
    UNKNOWN = "未分類"


class Frequency(Enum):
    """発生頻度"""
    MONTHLY = "月次"
    BIMONTHLY = "隔月"
    QUARTERLY = "四半期"
    SEMIANNUAL = "半期"
    ANNUAL = "年次"
    IRREGULAR = "不定期"


@dataclass
class ExpensePattern:
    """経費パターン"""
    account: str  # 勘定科目
    description: str  # 摘要
    expense_type: ExpenseType
    frequency: Optional[Frequency]
    avg_amount: float
    occurrence_count: int
    months_occurred: List[int]  # 発生月リスト


class ExpenseAnalyzer:
    """経費分析クラス"""

    def __init__(
        self,
        min_occurrences_for_recurring: int = 3,
        fiscal_year_end_month: int = 3
    ):
        """
        Args:
            min_occurrences_for_recurring: 継続と判定する最小出現回数
            fiscal_year_end_month: 決算月
        """
        self.min_occurrences = min_occurrences_for_recurring
        self.fiscal_year_end_month = fiscal_year_end_month

    def create_monthly_summary(
        self,
        df: pd.DataFrame,
        account_column: str = '借方勘定科目',
        amount_column: str = '借方金額',
        target_accounts: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        月次推移表を作成

        Args:
            df: 仕訳データ
            account_column: 勘定科目カラム
            amount_column: 金額カラム
            target_accounts: 対象勘定科目リスト（Noneの場合は全て）

        Returns:
            月次推移表（行=勘定科目、列=年月）
        """
        # 対象データをフィルタ
        work_df = df.copy()
        if target_accounts:
            work_df = work_df[work_df[account_column].isin(target_accounts)]

        # 年月でグループ化
        monthly = work_df.groupby(
            [work_df['年月'], work_df[account_column]]
        )[amount_column].sum().reset_index()

        # ピボットテーブルに変換
        pivot = monthly.pivot(
            index=account_column,
            columns='年月',
            values=amount_column
        ).fillna(0)

        # カラムをソート
        pivot = pivot.reindex(sorted(pivot.columns), axis=1)

        # 合計行を追加
        pivot.loc['合計'] = pivot.sum()

        return pivot

    def create_monthly_detail(
        self,
        df: pd.DataFrame,
        account_column: str = '借方勘定科目',
        description_column: str = '摘要',
        amount_column: str = '借方金額',
        target_accounts: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        勘定科目+摘要別の月次推移表を作成

        Args:
            df: 仕訳データ
            account_column: 勘定科目カラム
            description_column: 摘要カラム
            amount_column: 金額カラム
            target_accounts: 対象勘定科目リスト

        Returns:
            詳細月次推移表
        """
        work_df = df.copy()
        if target_accounts:
            work_df = work_df[work_df[account_column].isin(target_accounts)]

        # 勘定科目+摘要でグループ化
        work_df['科目_摘要'] = work_df[account_column].fillna('') + '｜' + work_df[description_column].fillna('')

        monthly = work_df.groupby(
            [work_df['年月'], work_df['科目_摘要']]
        )[amount_column].sum().reset_index()

        pivot = monthly.pivot(
            index='科目_摘要',
            columns='年月',
            values=amount_column
        ).fillna(0)

        pivot = pivot.reindex(sorted(pivot.columns), axis=1)

        return pivot

    def analyze_patterns(
        self,
        df: pd.DataFrame,
        account_column: str = '借方勘定科目',
        description_column: str = '摘要',
        amount_column: str = '借方金額',
    ) -> List[ExpensePattern]:
        """
        経費パターンを分析

        Args:
            df: 仕訳データ

        Returns:
            経費パターンリスト
        """
        patterns = []

        # 勘定科目+摘要でグループ化
        grouped = df.groupby([account_column, description_column])

        for (account, description), group in grouped:
            if pd.isna(account) or account == '':
                continue

            occurrence_count = len(group)
            months = group['日付'].dt.month.unique().tolist()
            avg_amount = group[amount_column].mean()

            # タイプと頻度を判定
            expense_type, frequency = self._classify_expense(
                occurrence_count,
                months,
                group['年月'].nunique()
            )

            patterns.append(ExpensePattern(
                account=account,
                description=description if pd.notna(description) else '',
                expense_type=expense_type,
                frequency=frequency,
                avg_amount=avg_amount,
                occurrence_count=occurrence_count,
                months_occurred=sorted(months)
            ))

        return patterns

    def _classify_expense(
        self,
        occurrence_count: int,
        months: List[int],
        unique_periods: int
    ) -> Tuple[ExpenseType, Optional[Frequency]]:
        """経費を分類"""
        if occurrence_count < self.min_occurrences:
            return ExpenseType.SPOT, None

        # 継続経費の頻度を判定
        if unique_periods >= 12:
            return ExpenseType.RECURRING, Frequency.MONTHLY
        elif unique_periods >= 6:
            return ExpenseType.RECURRING, Frequency.BIMONTHLY
        elif unique_periods >= 4:
            return ExpenseType.RECURRING, Frequency.QUARTERLY
        elif unique_periods >= 2:
            return ExpenseType.RECURRING, Frequency.SEMIANNUAL
        elif unique_periods >= 1:
            return ExpenseType.RECURRING, Frequency.ANNUAL
        else:
            return ExpenseType.RECURRING, Frequency.IRREGULAR

    def get_expense_accounts(self) -> List[str]:
        """一般的な経費勘定科目リスト"""
        return [
            # 販管費
            '役員報酬', '給料手当', '賃金', '賞与', '雑給',
            '退職金', '法定福利費', '福利厚生費',
            '広告宣伝費', '交際費', '会議費', '旅費交通費',
            '通信費', '消耗品費', '事務用品費', '水道光熱費',
            '新聞図書費', '諸会費', '支払手数料', '車両費',
            '地代家賃', 'リース料', '賃借料', '保険料',
            '租税公課', '減価償却費', '修繕費', '雑費',
            '外注費', '支払報酬', '研究開発費', '採用教育費',
            # 原価
            '仕入高', '外注加工費', '材料費', '労務費',
        ]

    def calculate_fiscal_year_totals(
        self,
        monthly_df: pd.DataFrame,
        fiscal_year_end_month: int = 3
    ) -> pd.DataFrame:
        """
        会計年度別の合計を計算

        Args:
            monthly_df: 月次推移表
            fiscal_year_end_month: 決算月

        Returns:
            年度別合計
        """
        result = {}

        for col in monthly_df.columns:
            period = col
            year = period.year
            month = period.month

            # 会計年度を判定
            if month > fiscal_year_end_month:
                fy = year + 1
            else:
                fy = year

            fy_label = f'FY{fy}'
            if fy_label not in result:
                result[fy_label] = monthly_df[col].copy()
            else:
                result[fy_label] = result[fy_label] + monthly_df[col]

        return pd.DataFrame(result)
