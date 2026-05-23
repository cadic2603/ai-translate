---
description: Instale o FFmpeg para que o AI Translate possa decodificar áudio e vídeo para geração de legendas, síntese de voz e dublagem de vídeo — necessário para funcionalidades de mídia.
---

# FFmpeg

FFmpeg é necessário para qualquer fluxo de áudio / vídeo:

- **Gerar legenda** — decodificação de áudio de origem para STT
- **Gerar voz** — combinação de clipes TTS com tempo em um arquivo
- **Dublagem** — STT → TTS → mux de volta para o vídeo
- **Tradução ao vivo** — quando a captura de áudio do sistema passa
  por `parec`

Não vem embutido — instale uma vez no seu sistema.

## Instalar

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    Ou, para uma build mais completa, habilite o
    [RPM Fusion](https://rpmfusion.org/Configuration) primeiro.

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    Baixe uma build estática de <https://www.gyan.dev/ffmpeg/builds/>
    (a build "release essentials" serve), descompacte, então adicione
    a pasta `bin/` ao seu PATH:

    1. Pressione **Win + R**, digite `sysdm.cpl`, pressione **Enter**
    2. **Avançado → Variáveis de Ambiente → Variáveis do sistema → Path → Editar**
    3. **Novo** → cole o caminho absoluto da pasta `bin` do FFmpeg
    4. **OK** em tudo, reinicie quaisquer terminais abertos

## Verificar

```bash
ffmpeg -version
```

Você deve ver um banner de versão com `--enable-libx264 --enable-libvpx`
na linha de configuração. Se você ver "command not found", a
instalação não terminou no PATH.

## Verificação pre-flight no app

As páginas Voz / Dublagem chamam `shutil.which("ffmpeg")` antes de
começar o trabalho. Se o FFmpeg não for encontrado, você verá um
diálogo de erro amigável com um link de volta para cá, não uma
tarefa parcialmente executada.

## Erro comum

| Erro | Significado |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` não está no PATH no momento em que a página tentou executá-lo. Instale (acima) e reinicie o app. |

No servidor MCP (`ait-mcp`), o mesmo erro é re-empacotado em uma
mensagem legível:

> *"FFmpeg é necessário para decodificar este arquivo de áudio/vídeo
> mas não está instalado ou não está no PATH. Instale o FFmpeg e
> tente novamente."*
