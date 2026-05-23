---
description: "Duble vídeos de ponta a ponta: transcreva o áudio, traduza a legenda, sintetize a fala no idioma destino e remixe-a no vídeo original."
---

# Dublagem de vídeo

Pipeline completo **STT → Traduzir → TTS → Mix** que produz um arquivo
de vídeo em outro idioma com a trilha de voz substituída. O áudio
original é descartado; a nova trilha de dublagem é sincronizada com
as legendas.

## O que você precisa

- **FFmpeg** no `PATH` — veja [Configuração FFmpeg](../setup/ffmpeg.md).
- Um backend STT (padrão: Whisper local, sem configuração)
- Um backend TTS — Edge TTS (padrão), ElevenLabs, Google Cloud TTS,
  Gemini TTS, ou **Piper TTS** (totalmente offline; vozes por idioma
  baixadas uma vez via **Configurações → Voz → Piper TTS → Baixar
  vozes agora**)
- Um **LLM** configurado para o passo de tradução

## Passo a passo

1. Clique em **Dublagem** na barra lateral.
2. Solte um ou mais arquivos de vídeo (`.mp4`, `.webm`, `.mkv`,
   `.avi`, `.mov`, `.wmv`).
3. Escolha o **Idioma fonte** (o idioma *falado* no vídeo) e o
   **Idioma destino** para o qual dublar.
4. Clique em **Iniciar dublagem** (`Ctrl+Enter`).
5. Observe o progresso por tarefa na tabela de histórico. Passa por
   quatro fases:

| Fase | Faixa | O que acontece |
|---|---|---|
| **STT** | 5–25% | Transcrevendo o áudio fonte |
| **Traduzir** | 25–50% | LLM traduzindo cada linha de legenda |
| **TTS** | 50–90% | Sintetizando voz idioma-destino para cada linha |
| **Mix** | 90–100% | FFmpeg substitui a trilha de áudio |

6. Quando completo, **Abra** a linha para reproduzir o vídeo dublado.

## Saídas

Para cada vídeo de entrada você obtém quatro arquivos no diretório
de saída:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← vídeo dublado
movie_subtitle_en.srt               ← legenda idioma original
movie_subtitle_fr.srt               ← legenda traduzida
movie_voice_fr.mp3                  ← trilha de voz sintetizada
```

## Retomar uma execução pausada / crashada

O pipeline faz checkpoint após cada fase. Se você pressionar **Parar**,
sair do app, ou crashar, pressionar **Continuar** na linha retoma da
última fase completada — você não paga novamente por STT ou tradução
se já estavam feitos.

Clique direito em uma entrada Done / Failed para estas opções:

- **Continuar** — retoma do último checkpoint sem re-prompt.
- **Re-dublar** — reabre o seletor de idioma; se você escolher um
  novo destino, os checkpoints traduzir e TTS são descartados (você
  não paga novamente por STT). Escolher o mesmo destino efetivamente
  reexecuta do último checkpoint, igual a Continuar.
- **Abrir** — reproduz o vídeo dublado.

## Avisos

!!! warning "Sincronização labial"
    A dublagem combina os *timestamps* do áudio fonte, não os
    movimentos labiais. Linhas traduzidas muito mais longas que o
    original soarão apressadas; muito mais curtas deixarão silêncio.
    Para dublagem profissional, geralmente re-tempora-se manualmente
    após esta passagem — é uma funcionalidade futura.

!!! tip "Verificações pre-flight"
    A página valida FFmpeg + as chaves do seu backend TTS antes de
    começar. Chave faltando → diálogo amigável, sem dublagem pela
    metade. Com **Piper TTS** selecionado, também verifica que a voz
    Piper por idioma está em disco; voz faltando → diálogo modal com
    botão **Abrir Configurações** que te leva à biblioteca de vozes,
    para que você não queime tempo de STT + tradução para falhar no
    passo TTS.

!!! tip "Mudar idioma destino"
    Em um re-target o pipeline descarta os checkpoints traduzir +
    TTS (seu conteúdo não é mais válido para o novo idioma) mas mantém
    o checkpoint STT — você economiza o custo de transcrição.

## Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Iniciar dublagem |
| `Ctrl+O` | Procurar |
| `Ctrl+F` | Foco em busca do histórico |
| `Ctrl+P` | Pausar fila ativa |
| `Ctrl+G` | Continuar (retomar) fila ativa |

`Ctrl+P` / `Ctrl+G` são suprimidos quando um campo de texto tem foco,
para não colidirem com digitação.
