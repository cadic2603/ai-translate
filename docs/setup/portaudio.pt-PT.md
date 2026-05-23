---
description: Captura de áudio de microfone multiplataforma para tradução ao vivo.
---

# Configuração do PortAudio (Microfone)

A funcionalidade de [Tradução ao vivo](../features/live-translation.md) utiliza o pacote Python `sounddevice`, que depende da biblioteca C PortAudio para aceder a dispositivos de microfone em todos os sistemas operativos. A maioria dos utilizadores necessita de instalar esta dependência ao nível do sistema.

## Windows
Os wheels pré-compilados para `sounddevice` e `PyAudio` normalmente agrupam o binário do PortAudio no Windows. A instalação manual em todo o sistema normalmente não é necessária. Se encontrar erros, certifique-se de que os seus controladores de áudio estão atualizados.

## macOS
Utilize o Homebrew para instalar o PortAudio:

```bash
brew install portaudio
```

## Linux
O nome do pacote depende da sua distribuição. O pacote de desenvolvimento (normalmente terminando em `-dev` ou `-devel`) deve ser instalado para que o Python possa construir as ligações C se um wheel pré-compilado não estiver disponível.

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

## Resolução de problemas

Se a aplicação continuar a reportar que não consegue aceder ao microfone após a instalação:

1. Certifique-se de que a sua aplicação de terminal (ou ambiente de ambiente de trabalho) tem permissão para aceder ao microfone (especialmente no macOS).
2. Reinicie a aplicação (ou o terminal/servidor MCP) para que esta adquira o novo caminho da biblioteca.
