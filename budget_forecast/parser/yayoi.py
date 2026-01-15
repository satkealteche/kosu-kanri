"""
弥生会計 仕訳日記帳パーサー（CSV/XLS/XLSX対応）
"""
import pandas as pd
import re
from datetime import datetime
from typing import Optional, Tuple, Union
from pathlib import Path
from io import StringIO, BytesIO


class YayoiParser:
    """弥生会計の仕訳日記帳をパースするクラス（CSV/Excel両対応）"""

    # 弥生会計CSVの標準カラム名（借方/貸方で分かれる）
    EXPECTED_COLUMNS = [
        '日付', '伝票No', '決算', '調整', '付箋1', '付箋2', 'タイプ', '生成元',
        '借方勘定科目', '借方補助科目', '借方部門', '借方税区分', '借方税計算区分', '借方金額', '借方税額',
        '貸方勘定科目', '貸方補助科目', '貸方部門', '貸方税区分', '貸方税計算区分', '貸方金額', '貸方消費税額',
        '摘要', '請求区分', '仕入税額控除', '期日', '備考', '仕訳メモ', '作業日付', '仕訳番号'
    ]

    def __init__(self, fiscal_year_end_month: int = 3):
        """
        Args:
            fiscal_year_end_month: 決算月（デフォルト3月）
        """
        self.fiscal_year_end_month = fiscal_year_end_month

    def parse(self, file_path_or_buffer, encoding: str = 'cp932', file_type: str = None) -> Tuple[pd.DataFrame, dict]:
        """
        弥生会計ファイルを読み込んでパースする（CSV/XLS/XLSX対応）

        Args:
            file_path_or_buffer: ファイルパスまたはファイルオブジェクト
            encoding: CSVの文字エンコーディング（弥生はShift-JIS/cp932が多い）
            file_type: ファイル形式 ('csv', 'xls', 'xlsx') - Noneの場合は自動判定

        Returns:
            Tuple[pd.DataFrame, dict]: パース済みデータフレームとメタ情報
        """
        # ファイル形式を判定
        if file_type is None:
            file_type = self._detect_file_type(file_path_or_buffer)

        # ファイル形式に応じて読み込み
        if file_type in ['xls', 'xlsx']:
            df, header_row = self._find_and_read_excel(file_path_or_buffer)
        else:
            df, header_row = self._find_and_read_csv(file_path_or_buffer, encoding)

        # 共通の後処理
        df = self._normalize_columns(df)
        df = self._parse_dates(df)
        df = self._parse_amounts(df)

        # 会計年度を追加
        df['会計年度'] = df['日付'].apply(self._get_fiscal_year)
        df['年月'] = df['日付'].dt.to_period('M')

        # メタ情報
        meta = {
            'total_records': len(df),
            'date_range': (df['日付'].min(), df['日付'].max()),
            'fiscal_years': sorted([fy for fy in df['会計年度'].unique().tolist() if fy is not None]),
            'header_row': header_row,
            'file_type': file_type
        }

        return df, meta

    # 後方互換性のためのエイリアス
    def parse_csv(self, file_path_or_buffer, encoding: str = 'cp932') -> Tuple[pd.DataFrame, dict]:
        """後方互換性のためのエイリアス"""
        return self.parse(file_path_or_buffer, encoding=encoding, file_type='csv')

    def _detect_file_type(self, file_path_or_buffer) -> str:
        """ファイル形式を自動判定"""
        # ファイル名から判定
        name = ''
        if hasattr(file_path_or_buffer, 'name'):
            name = file_path_or_buffer.name.lower()
        elif isinstance(file_path_or_buffer, (str, Path)):
            name = str(file_path_or_buffer).lower()

        if name.endswith('.xlsx'):
            return 'xlsx'
        elif name.endswith('.xls'):
            return 'xls'
        elif name.endswith('.csv'):
            return 'csv'

        # バイト列の先頭で判定
        if hasattr(file_path_or_buffer, 'read'):
            pos = file_path_or_buffer.tell() if hasattr(file_path_or_buffer, 'tell') else 0
            header = file_path_or_buffer.read(8)
            file_path_or_buffer.seek(pos)

            if header:
                # XLSXはZIPファイル
                if header[:4] == b'PK\x03\x04':
                    return 'xlsx'
                # XLSはOLE形式
                elif header[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
                    return 'xls'

        return 'csv'

    def _find_and_read_excel(self, file_path_or_buffer) -> Tuple[pd.DataFrame, int]:
        """Excelファイルを読み込む"""
        # バイト列として読み込み
        if hasattr(file_path_or_buffer, 'read'):
            content = file_path_or_buffer.read()
            file_path_or_buffer = BytesIO(content)

        # まずプレビューでヘッダー行を探す
        try:
            preview_df = pd.read_excel(file_path_or_buffer, header=None, nrows=20, dtype=str)
        except Exception as e:
            raise ValueError(f"Excelファイルの読み込みに失敗しました: {e}")

        # '日付'を含む行を探す
        header_row = 0
        for idx, row in preview_df.iterrows():
            row_str = ' '.join([str(cell) for cell in row.values if pd.notna(cell)])
            if '日付' in row_str and ('伝票' in row_str or '勘定' in row_str):
                header_row = idx
                break

        # ファイルポインタをリセット
        if hasattr(file_path_or_buffer, 'seek'):
            file_path_or_buffer.seek(0)

        # 本読み込み
        df = pd.read_excel(
            file_path_or_buffer,
            header=header_row,
            dtype=str,
            na_values=['', ' ', '　']
        )

        return df, header_row

    def _find_and_read_csv(self, file_path_or_buffer, encoding: str) -> Tuple[pd.DataFrame, int]:
        """CSVファイルを読み込む"""
        # ファイル内容を全て読み込む
        if hasattr(file_path_or_buffer, 'read'):
            content = file_path_or_buffer.read()
            if isinstance(content, bytes):
                try:
                    content = content.decode(encoding)
                except:
                    content = content.decode('utf-8')
        else:
            with open(file_path_or_buffer, 'r', encoding=encoding) as f:
                content = f.read()

        lines = content.strip().split('\n')

        # '日付'を含む行（ヘッダー行）を探す
        header_row = 0
        for idx, line in enumerate(lines):
            if '日付' in line and ('伝票' in line or '勘定' in line):
                header_row = idx
                break

        # ヘッダー行以降のデータを読み込む
        data_lines = lines[header_row:]
        data_content = '\n'.join(data_lines)

        df = pd.read_csv(
            StringIO(data_content),
            dtype=str,
            na_values=['', ' ', '　'],
            on_bad_lines='skip'
        )

        return df, header_row

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """カラム名を正規化"""
        # 空白を除去
        df.columns = [str(col).strip() for col in df.columns]

        # 重複カラム名を借方/貸方で区別
        cols = []
        debit_found = set()
        credit_found = set()

        for col in df.columns:
            col_clean = col.strip()

            # 借方/貸方の区別がない場合、出現順で判定
            if col_clean in ['勘定科目', '補助科目', '部門', '税区分', '税計算区分', '金額', '税額', '消費税額']:
                if col_clean not in debit_found:
                    cols.append(f'借方{col_clean}')
                    debit_found.add(col_clean)
                elif col_clean not in credit_found:
                    new_col = f'貸方{col_clean}'
                    if col_clean == '税額':
                        new_col = '貸方消費税額'
                    cols.append(new_col)
                    credit_found.add(col_clean)
                else:
                    cols.append(col_clean)
            else:
                cols.append(col_clean)

        df.columns = cols
        return df

    def _parse_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """日付を変換"""
        if '日付' not in df.columns:
            raise ValueError("'日付'カラムが見つかりません")

        def convert_date(val):
            if pd.isna(val):
                return pd.NaT
            val = str(val).strip()

            # 令和/平成/昭和の和暦変換
            wareki_patterns = [
                (r'令和(\d+)年(\d+)月(\d+)日', 2018),  # 令和1年 = 2019年
                (r'R(\d+)[./](\d+)[./](\d+)', 2018),
                (r'平成(\d+)年(\d+)月(\d+)日', 1988),  # 平成1年 = 1989年
                (r'H(\d+)[./](\d+)[./](\d+)', 1988),
            ]

            for pattern, base_year in wareki_patterns:
                match = re.match(pattern, val)
                if match:
                    year = int(match.group(1)) + base_year
                    month = int(match.group(2))
                    day = int(match.group(3))
                    try:
                        return datetime(year, month, day)
                    except:
                        return pd.NaT

            # 西暦形式
            try:
                return pd.to_datetime(val)
            except:
                return pd.NaT

        df['日付'] = df['日付'].apply(convert_date)
        df = df.dropna(subset=['日付'])

        return df

    def _parse_amounts(self, df: pd.DataFrame) -> pd.DataFrame:
        """金額を数値に変換"""
        amount_cols = ['借方金額', '貸方金額', '借方税額', '貸方消費税額']

        for col in amount_cols:
            if col in df.columns:
                df[col] = df[col].apply(self._clean_amount)

        return df

    def _clean_amount(self, val) -> float:
        """金額文字列を数値に変換"""
        if pd.isna(val):
            return 0.0

        val = str(val).strip()
        # カンマ、括弧、円記号を除去
        val = re.sub(r'[,，円¥\s]', '', val)

        # 括弧は負数
        if val.startswith('(') or val.startswith('（'):
            val = '-' + re.sub(r'[()（）]', '', val)

        try:
            return float(val)
        except:
            return 0.0

    def _get_fiscal_year(self, date) -> Optional[int]:
        """日付から会計年度を取得"""
        if pd.isna(date):
            return None

        year = date.year
        month = date.month

        # 決算月より後なら次の年度
        if month > self.fiscal_year_end_month:
            return year + 1
        else:
            return year
