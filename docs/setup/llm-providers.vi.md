---
description: "Cấu hình các nhà cung cấp LLM cho dịch: Google Gemini (khuyến nghị), endpoint tương thích OpenAI, hoặc bất kỳ nhà cung cấp tùy chỉnh nào có API key."
---

# Nhà cung cấp LLM

Pipeline dịch gọi Large Language Model để dịch thực sự. Bạn có thể
cấu hình một hoặc nhiều; bộ chọn model theo trang cho phép mỗi trang
dùng model khác nhau.

## Google Gemini (khuyến nghị cho lần đầu cài đặt) {: #google-gemini-recommended-for-first-time-setup }

Gói miễn phí hào phóng và đủ tốt cho hầu hết nhu cầu cá nhân.

1. Vào <https://aistudio.google.com/apikey>
2. Nhấp **Create API key** (đăng nhập với tài khoản Google)
3. Sao chép key (dạng `AIza...`)
4. Trong ứng dụng desktop: **Cài đặt → LLM → Gemini API key** → dán → **Lưu**
5. Chọn model mặc định trong dropdown **Model Gemini mặc định**.
   Danh sách của Google thường nhìn như:

    - **Flash** (ví dụ `gemini-2.5-flash`) — nhanh, gói miễn phí hào
      phóng, chất lượng tốt. Khuyến nghị bắt đầu.
    - **Pro** — chậm hơn, chất lượng cao hơn, đắt hơn.
    - **Flash-lite** — nhanh nhất, rẻ nhất, chất lượng thấp hơn.

    Tên model cụ thể có sẵn phụ thuộc vào những gì Google đã rollout
    cho tài khoản của bạn; chọn cái nào có chứa `flash` cho mặc định
    cân bằng.

Xong. Key được lưu trong keychain OS, không phải plain text.

### Chế độ Vertex AI (enterprise)

Bên trong khối cấu hình Gemini, một cặp radio cho phép bạn chuyển từ
**Developer API** sang **Vertex AI** — cùng các model Gemini, được
tính phí qua tài khoản GCP của bạn, với điều khiển cấp tổ chức (VPC-SC,
audit log, lưu trữ dữ liệu theo vùng).

1. Trong **Cài đặt → LLM**, chuyển radio Gemini từ **Developer API**
   sang **Vertex AI**
2. Điền:
    - **Project** — ID dự án GCP của bạn
    - **Location** — một vùng Vertex (mặc định `us-central1`)
    - **Đường dẫn credentials** *(tùy chọn)* — đường dẫn tới file JSON
      service account. Để trống để dùng Application Default Credentials
      (`gcloud auth application-default login`)
3. **Lưu**. Dropdown model điền lại từ Vertex khi project đã đặt.

Refresh OAuth được `google-genai` xử lý tự động. Đường dẫn JSON service
account được lưu plaintext có chủ đích (*đường dẫn* không phải là
secret — nội dung file mới là, và chúng nằm trên ổ đĩa nơi best practice
của Google giữ chúng).

## OpenAI / tương thích OpenAI

Mọi thứ expose REST API tương thích OpenAI đều chạy được — bản thân
OpenAI, Anthropic qua [LiteLLM proxy](https://docs.litellm.ai), Ollama
local, LM Studio, vLLM, Together.ai, Groq, v.v.

Trong **Cài đặt → LLM**:

1. Nhấp **Thêm nhà cung cấp tùy chỉnh**
2. Điền:
    - **Tên** — một nhãn như "OpenAI" / "Local Ollama" / "Anthropic"
    - **Endpoint API** — base URL (ví dụ `https://api.openai.com/v1` hoặc
      `http://localhost:11434/v1` cho Ollama)
    - **API key** — để trống cho endpoint local không cần xác thực
    - **Models** — danh sách phân tách bằng dấu phẩy (ví dụ
      `gpt-4o-mini, gpt-4o, gpt-3.5-turbo`)
3. Nhấp **Lưu**.

Các nhà cung cấp tùy chỉnh được lưu dưới dạng blob JSON trong keychain
OS (bao gồm API key).

## Đổi model mặc định

Dropdown **Model Gemini mặc định** trong **Cài đặt → LLM** đặt fallback
được dùng bởi mọi trang tính năng không có bộ chọn riêng.

Trang có bộ chọn model riêng:

- **Dịch văn bản** — `Tab Cài đặt Dịch văn bản → Model mặc định`
- **Dịch tài liệu** — chọn theo tác vụ; fallback về mặc định
- **Phụ đề / Giọng nói / Lồng tiếng / Trực tiếp / Trích xuất văn bản** —
  mỗi cái có mặc định riêng trong tab Cài đặt của nó

Cách này cho phép trộn-và-khớp: Flash miễn phí cho live, Pro cho tài
liệu lớn, Ollama local cho dữ liệu nhạy cảm.

## Key được lưu ở đâu

| OS | Lưu trữ |
|---|---|
| **macOS** | Keychain (keychain login) |
| **Windows** | Credential Manager |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (không có daemon)** | Fallback plaintext INI ở `~/.config/ai-translate/settings.ini` |

Giá trị fallback INI được migrate sang keychain ở lần đọc đầu tiên khi
keychain trở nên có sẵn — không cần bước thủ công.

## Cài đặt headless / server

Không có phiên desktop, bạn vẫn có thể đặt key qua CLI `keyring` của
Python (sau `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Custom providers (dán blob JSON — xem UI Cài đặt cho schema)
uv run keyring set ai-translate llm/custom_providers
```

Hoặc đặt cùng các key INI trực tiếp trong `settings.ini` — ứng dụng
migrate sang keychain ở lần đọc đầu tiên. File nằm ở:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Kiểm tra cài đặt

Kiểm tra nhanh:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target French --quiet
cat /tmp/x_translated__fr.txt
```

Nếu bạn thấy "Bonjour le monde." — bạn đã xong.

## Lỗi thường gặp

| Lỗi | Nguyên nhân có thể |
|---|---|
| `AUTH_ERROR` | API key sai / hết hạn. Dán lại trong Cài đặt. |
| `QUOTA_ERROR` | Vượt số request mỗi ngày của gói miễn phí. Chờ, hoặc trả phí. |
| `MODEL_NOT_FOUND` | Danh sách `models` của nhà cung cấp tùy chỉnh không bao gồm model đã yêu cầu. |
| `VISION_NOT_SUPPORTED` | Model bạn chọn không xử lý được input ảnh. Dùng biến thể `flash` / `pro` / `vision`. |

Xem [Khắc phục sự cố](../troubleshooting.md) để biết thêm.
