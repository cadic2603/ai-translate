---
description: Captura de áudio de microfone multiplataforma para tradução ao vivo.
---

# Configuração do PortAudio (Microfone)

O recurso de [Tradução ao vivo](../features/live-translation.md) usa o pacote Python `sounddevice`, que depende da biblioteca C PortAudio para acessar dispositivos de microfone em todos os sistemas operacionais. A maioria dos usuários precisa instalar essa dependência no nível do sistema.

## Windows
Os wheels pré-compilados para `sounddevice` e `PyAudio` normalmente empacotam o binário do PortAudio no Windows. A instalação manual em todo o sistema normalmente não é necessária. Se você encontrar erros, verifique se os drivers de áudio estão atualizados.

## macOS
Use o Homebrew para instalar o PortAudio:

```bash
brew install portaudio
```

## Linux
O nome do pacote depende da sua distribuição. O pacote de desenvolvimento (geralmente terminando em `-dev` ou `-devel`) deve ser instalado para que o Python possa construir as ligações C se um wheel pré-compilado não estiver disponível.

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## Solução de problemas

Se o aplicativo continuar relatando que não pode acessar o microfone após a instalação:

1. Certifique-se de que seu aplicativo de terminal (ou ambiente de área de trabalho) tenha permissão para acessar o microfone (especialmente no macOS).
2. Reinicie o aplicativo (ou o terminal/servidor MCP) para que ele adquira o novo caminho da biblioteca.
