---
description: AI Translate の Live ページのために Linux、macOS、Windows でシステムオーディオをキャプチャ — コンピュータで再生されている任意の音声をリアルタイムに翻訳。
---

# システムオーディオキャプチャ（Live）

**[ライブ翻訳](../features/live-translation.md)**ページは、**システム
オーディオ**（スピーカーで再生されているすべて）をキャプチャできるので、
あらゆるメディアを字幕 / 翻訳できます — Zoom 通話、YouTube、Netflix、
ゲーム、システム音。

**設定 → Live → オーディオソース**（または Live ページ上部の
コンボ）で、選択：

- **マイク** — マイクのみ
- **システムオーディオ** — スピーカーで再生されているもののみ
- **両方** — 両方をミックス（メディアの上にナレーションする、または
  ハイブリッド会議をキャプチャするのに適している）

**システムオーディオ**または**両方**を選択すると、アプリは OS の
正しいキャプチャバックエンドにディスパッチします。OS の前提条件が
満たされていない場合、クリック可能なインストールリンク付きのインライン
警告バナーが表示されるので、何かが欠落していることを知るためにセッション
を開始する必要はありません。

## Linux (PulseAudio / PipeWire)

すべての現代的なディストロでアウト・オブ・ザ・ボックスで動作します。

アプリは `parec`（PulseAudio Recorder）を使用してデフォルトシンクの
**モニターソース**にタップします。PipeWire の PulseAudio 互換性 shim
がこれを透過的にします — 生の PulseAudio は必要ありません。

```bash
parec --version    # 何かを印刷するはず
```

`parec` が欠落している場合、警告バナーはディストロのパッケージ
マネージャーを検出し、正確なインストールコマンドをインラインで
表示します — たとえば：

> システムオーディオキャプチャには PulseAudio または PipeWire が必要 — `sudo apt-get install pulseaudio` を実行。

apt-get / dnf / pacman / zypper / apk で検出されます；コマンドを
直接ターミナルにコピー＆ペーストできます。

## macOS

CoreAudio はシステムオーディオをネイティブに公開しないので、**仮想
ループバックデバイス**が必要です — 次のいずれかをインストール：

- **[BlackHole](https://existential.audio/blackhole/)** — 無料、オープンソース
- **[Loopback](https://rogueamoeba.com/loopback/)** — 有料、洗練された GUI
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — レガシー無料オプション
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — 有料

アプリは `ffmpeg -f avfoundation -list_devices` を介してこれらの
いずれも自動検出し、最初の一致を使用します。ループバックをデフォルト
出力 / 入力として設定する必要はありません — キャプチャは `ffmpeg`
の avfoundation バックエンドを通じて直接行われます。

インストール後、Live ページのコンボで**システムオーディオ**を選択
するだけで、警告バナーは消えます。

## Windows

ネイティブ — ほとんどの場合、**追加のソフトウェアは不要**。

アプリは Python パッケージ
[`soundcard`](https://github.com/bastibe/SoundCard)（Windows ではアプリ
と一緒に自動的にインストールされる）を通じて **WASAPI loopback** と
直接対話します。これは Tauri / Rust デスクトップアプリが使用するのと
同じネイティブループバック API です；仮想ケーブルなしでデフォルトの
スピーカー出力をキャプチャします。

何らかの理由で WASAPI loopback が利用できない場合（古い Windows
バージョン、異常なオーディオドライバ）、アプリは仮想ループバック
DirectShow デバイスに対して `ffmpeg -f dshow` にフォールバックし
ます。次のいずれかを選択：

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — 無料、`virtual-audio-capturer` を提供
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — 無料、`CABLE Output (VB-Audio Virtual Cable)` として提供
- **Stereo Mix (Realtek Audio)** — レガシーのオンボードオプション、デフォルトでよく無効化されている

アプリはこれらを順番にプローブし、最初に存在するものを使用します。

## なぜ「両方」があなたの声 AND システムオーディオを拾うのか

**両方**モードでは、アプリは並列に 2 つのキャプチャストリームを開きます
— `sounddevice` を介したマイク、上記の OS 固有のバックエンドを介した
システムオーディオ — そしてサンプルブロック粒度でそれらをミックス
します。これはビデオの上にナレーションするか、ハイブリッド会議の
両側をキャプチャするための正しいモードです（あなたの声と
スピーカーの参加者）。

> **ヒント：** エコーが聞こえたり、字幕が重複したりする場合、あなたの
> マイクを通してシステムオーディオが届いています（大きなスピーカー →
> マイクが拾う）。**システムオーディオ**のみに切り替えるか、ヘッド
> フォンを使用してください。

## トラブルシューティング

| 症状 | 考えられる原因 |
|---|---|
| Live ページが開始するが字幕なし | 間違ったオーディオソースが選択されている、またはデフォルトのマイクがミュートされている |
| あなたの声の字幕は出るが YouTube ビデオの字幕は出ない | システムオーディオの前提条件がインストールされていない（バナーがインストール手順を表示するはず） |
| 字幕が二重（エコー） | 「両方」モードがシステムオーディオを 2 回キャプチャ — 一度はスピーカーからマイク経由、一度はループバック経由。システムオーディオのみに切り替えるかヘッドフォンを使用 |
| 不足しているソフトウェアをインストール後もバナーが表示されたまま | タブを切り替えて戻る — バナーはページ表示時に再チェックする |
| macOS: BlackHole はインストール済みだがバナーがまだ表示 | BlackHole が `ffmpeg -f avfoundation -list_devices true -i ""` のオーディオデバイスリストにあることを確認；アプリがそこで見る必要がある |
| Windows: エラーがないにもかかわらず WASAPI loopback が失敗 | フォールバックとして VB-Audio Virtual Cable のインストールを試みる；古い Windows バージョンや一部のオーディオドライバは `soundcard` 経由でループバックを公開しない |
