# SoundMaker

A headless Raspberry Pi audio appliance that streams internet radio on boot and seamlessly switches to AirPlay when an iPhone or Mac connects. When AirPlay disconnects, streaming resumes automatically. Physical LEDs indicate the current audio source.

## Quick Start

```bash
# Transfer files to Pi
scp *.py *.sh goorlavi@PI_IP:/home/goorlavi/

# SSH and install
ssh goorlavi@PI_IP
chmod +x install.sh
sudo ./install.sh
```

## Documentation

| Document                                       | Description                                                  |
| ---------------------------------------------- | ------------------------------------------------------------ |
| [Overview](docs/overview.md)                   | Project goals, features, architecture, technologies          |
| [Technical Context](docs/technical-context.md) | Deep dive: hardware, services, IPC, configs, troubleshooting |
| [Installation Guide](docs/installation.md)     | Full installation instructions (automated + manual)          |

## Status Commands

```bash
sudo systemctl status soundmaker.service      # Main service
sudo journalctl -u soundmaker.service -f      # Live logs
```
