# LangAlpha

LangAlpha は、workspace を中心にした汎用 Agent プラットフォームです。PTC の
プログラム実行、Flash 会話、sandbox、Skills、MCP、自動化、ファイル成果物、
source provenance を提供します。

コアランタイムは特定の業務領域に依存しません。workspace ごとに永続 sandbox を
持ち、会話・実行状態・チェックポイントは PostgreSQL に保存され、SSE は Redis に
より再接続に対応します。汎用 MCP は workspace 単位で設定し、資格情報は Vault に
保存できます。

起動方法、アーキテクチャ、開発コマンドはルートの [README](../README.md) を
参照してください。
