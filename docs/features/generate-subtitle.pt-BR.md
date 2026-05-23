---
description: Gere legendas SRT, VTT, ASS ou SSA de qualquer áudio ou vídeo — usa Whisper ou Google Cloud Speech-to-Text para transcrição de alta qualidade.
---

# Gerar legenda (STT)

Transcreve áudio ou vídeo em legendas com timing. Capta a fala e
emite SRT / VTT / ASS / SSA — com tradução opcional na mesma passagem.

## O que você precisa

- **FFmpeg** no `PATH` para decodificação áudio/vídeo — veja [Configuração FFmpeg](../setup/ffmpeg.md).
- Um backend de transcrição, um de:
    - **faster-whisper** — local, offline, grátis (padrão; sem configuração necessária)
    - **Google Cloud Speech-to-Text** — cloud, pago, mais preciso em áudio ruidoso. Veja [Configuração Google Cloud](../setup/google-cloud.md).
    - **Soniox** — cloud, pago, tempo real e diarização de falantes. Veja [Configuração Soniox](../setup/soniox.md).

## Passo a passo

1. Clique em **Gerar legenda** na barra lateral.
2. Solte um ou mais arquivos áudio / vídeo (`.mp3`, `.wav`, `.m4a`,
   `.flac`, `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`, `.avi`,
   `.mov`, `.wmv`).
3. Escolha o **Idioma fonte** (o idioma *falado* no áudio) — deixe em
   `Detecção automática` para o Whisper descobrir.
4. Escolha um **Idioma destino** — escolha `Sem tradução` para
   transcrição simples, ou qualquer um dos 45 idiomas suportados para
   traduzir a transcrição na mesma passagem.
5. Escolha o **Formato de saída** (SRT / VTT / ASS / SSA).
6. Clique em **Gerar** (ou `Ctrl+Enter`).
7. Observe a fila. **Abra** a linha quando terminar.

## Escolha do formato

| Formato | Melhor para |
|---|---|
| **SRT** | Universal — quase todo player suporta |
| **VTT** | Elementos `<track>` de HTML5 `<video>` |
| **ASS / SSA** | Karaokê, legendas estilizadas, fluxos fansub |

Os quatro formatos fazem round-trip pelo mesmo parser, então você
pode trocar o formato de saída em uma re-tradução sem perder o timing.

## Tamanho do modelo Whisper

Troque em **Configurações → Legenda**:

| Modelo | Tamanho | Velocidade | Precisão |
|---|---|---|---|
| `tiny` | ~75 MB | muito rápido | baixa |
| `base` (padrão) | ~150 MB | rápido | decente |
| `small` | ~500 MB | médio | bom |
| `medium` | ~1.5 GB | lento | alto |
| `large` | ~3 GB | muito lento | melhor |

Modelos baixam no primeiro uso e ficam cacheados localmente. Em
conexão lenta a primeira execução parece longa; as seguintes são rápidas.

## Comparação de métodos STT

| Backend | Custo | Online? | Diarização | Idiomas |
|---|---|---|---|---|
| **Whisper** (local) | Grátis | Não | Não | 99 |
| **Google Cloud STT** | Pago | Sim | Sim (modelo `latest_long`) | 125+ |
| **Soniox** | Pago | Sim | Sim (rótulos por token) | 60+ |

Troque em **Configurações → Legenda → Método STT**.

## Dicas

- **Botão Parar** — interrompe um batch em andamento. Arquivos
  enfileirados atrás do ativo permanecem na fila; você pode retomar depois.
- **Re-gerar** — clique direito em uma entrada Done para reexecutar
  com formato / idioma / método STT diferente.
- **Áudio longo** — Whisper lida bem com horas de áudio; orçamente
  ~1 minuto de processamento por minuto de áudio em CPU com modelo `base`.

## Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Gerar |
| `Ctrl+O` | Procurar |
| `Ctrl+F` | Foco em busca do histórico |
