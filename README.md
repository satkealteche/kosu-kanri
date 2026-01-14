# OuttoTeam

Outlookの予定を週次でまとめて、毎週月曜日にTeamsのチャットに自動投稿するツールです。

## できること

- Outlookカレンダーから今週の予定を取得
- 日付ごとにグループ化した見やすいサマリーを生成
- Teamsの指定したチャットに自動投稿

## 必要なもの

- Python 3.8以上
- Microsoft 365アカウント（会社/学校のOutlookとTeams）
- Azure ADでのアプリ登録（下記手順で説明）

---

## セットアップ手順

### Step 1: Pythonのインストール確認

```bash
python --version
```

Python 3.8以上が表示されればOKです。

### Step 2: 必要なライブラリをインストール

```bash
pip install -r requirements.txt
```

### Step 3: Azure ADでアプリを登録

Microsoft Graph APIを使うために、Azureでアプリを登録する必要があります。

1. **Azure Portal** にアクセス: https://portal.azure.com

2. **「Azure Active Directory」** を選択

3. **「アプリの登録」** → **「新規登録」** をクリック

4. アプリ情報を入力:
   - **名前**: `OuttoTeam`（任意）
   - **サポートされているアカウントの種類**: 「この組織ディレクトリのみに含まれるアカウント」を選択
   - **リダイレクトURI**: 空欄のままでOK

5. **「登録」** をクリック

6. 表示された画面から以下をメモ:
   - **アプリケーション (クライアント) ID** → `CLIENT_ID`
   - **ディレクトリ (テナント) ID** → `TENANT_ID`

### Step 4: APIアクセス許可を追加

1. 左メニューの **「APIのアクセス許可」** をクリック

2. **「アクセス許可の追加」** → **「Microsoft Graph」** → **「委任されたアクセス許可」**

3. 以下の権限を検索して追加:
   - `Calendars.Read` （カレンダー読み取り）
   - `Chat.ReadWrite` （チャット読み書き）

4. **「アクセス許可の追加」** をクリック

### Step 5: パブリッククライアントフローを有効化

1. 左メニューの **「認証」** をクリック

2. 下にスクロールして **「パブリック クライアント フローを許可する」** を **「はい」** に設定

3. **「保存」** をクリック

### Step 6: 環境変数を設定

1. `.env.example` をコピーして `.env` を作成:

```bash
cp .env.example .env
```

2. `.env` ファイルを編集して、Step 3でメモした値を設定:

```
CLIENT_ID=ここにクライアントIDを貼り付け
TENANT_ID=ここにテナントIDを貼り付け
TEAMS_CHAT_ID=（後で設定）
```

### Step 7: 初回認証を実行

```bash
python main.py --chats
```

ブラウザでMicrosoftにログインするよう案内が表示されます。
表示されたURLにアクセスし、コードを入力して認証してください。

認証成功後、参加中のチャット一覧が表示されます。

### Step 8: TEAMS_CHAT_IDを設定

Step 7で表示されたチャット一覧から、投稿先のチャットIDをコピーして `.env` に設定:

```
TEAMS_CHAT_ID=19:xxxxxxxx@thread.v2
```

**ヒント**: 自分自身とのチャット（メモ用）に投稿したい場合は、
Teamsで自分にメッセージを送ってからこのコマンドを実行すると、そのチャットが一覧に表示されます。

---

## 使い方

### 手動実行

```bash
python main.py
```

今週の予定を取得して、Teamsに投稿します。

### チャット一覧を確認

```bash
python main.py --chats
```

---

## 毎週月曜日に自動実行する方法

### Windows（タスクスケジューラ）

1. 「タスクスケジューラ」を開く
2. 「タスクの作成」をクリック
3. トリガー: 「毎週」→「月曜日」→ 時刻を設定
4. 操作: `python` のパスと `main.py` のパスを設定

### Mac/Linux（cron）

```bash
crontab -e
```

以下を追加（毎週月曜9時に実行）:

```
0 9 * * 1 cd /path/to/OuttoTeam && python main.py
```

---

## ファイル構成

```
OuttoTeam/
├── main.py            # メインスクリプト
├── config.py          # 設定管理
├── outlook_client.py  # Outlookカレンダー取得
├── teams_client.py    # Teamsチャット投稿
├── requirements.txt   # 依存ライブラリ
├── .env.example       # 環境変数テンプレート
├── .env               # 環境変数（自分で作成）
└── README.md          # このファイル
```

---

## トラブルシューティング

### 「権限がありません」エラー

- Azure PortalでAPIアクセス許可が正しく設定されているか確認
- 組織の管理者による同意が必要な場合があります

### 認証が毎回必要になる

- `token_cache.json` が作成されているか確認
- ファイルの書き込み権限があるか確認

### チャット一覧が空

- Teamsで何かチャットを開始してから再実行

---

## ライセンス

MIT License
