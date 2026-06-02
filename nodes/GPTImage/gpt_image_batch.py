"""GPT Image 2 batch text-to-image node."""

import csv
import hashlib
import time
import concurrent.futures
import re
import zipfile
from pathlib import Path
from datetime import datetime
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import requests

from ..Sora2.kuai_utils import env_or, http_headers_auth_only
from .gpt_image import SIZE_MAP, _extract_urls

try:
    import folder_paths
    HAS_FOLDER_PATHS = True
except ImportError:
    HAS_FOLDER_PATHS = False


RESULT_COLUMNS = ["status", "error_reason", "image_urls", "local_paths", "file_names"]
TEXT_EXCEL_RESULT_HEADERS = ["提示词", "尺寸", "状态", "失败原因", "保存路径", "文件名"]
RETRY_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def _comfy_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _input_csv_files() -> list:
    if not HAS_FOLDER_PATHS:
        return [""]
    try:
        input_dir = Path(folder_paths.get_input_directory())
        if not input_dir.exists():
            return [""]
        files = [
            str(path.relative_to(input_dir))
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".csv"
        ]
        return sorted(files) or [""]
    except Exception:
        return [""]


def _input_excel_files() -> list:
    if not HAS_FOLDER_PATHS:
        return [""]
    try:
        input_dir = Path(folder_paths.get_input_directory())
        if not input_dir.exists():
            return [""]
        files = [
            str(path.relative_to(input_dir))
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".xlsx"
        ]
        return sorted(files) or [""]
    except Exception:
        return [""]


def _resolve_csv_path(csv_file: str, csv_path: str) -> Path:
    csv_file = str(csv_file or "").strip()
    csv_path = str(csv_path or "").strip()

    if csv_file:
        if not HAS_FOLDER_PATHS:
            raise RuntimeError("folder_paths 不可用，请使用 csv_path")
        input_dir = Path(folder_paths.get_input_directory())
        direct = input_dir / csv_file
        if direct.exists():
            return direct
        filename = Path(csv_file).name
        for path in input_dir.rglob(filename):
            if path.is_file() and path.suffix.lower() == ".csv":
                return path
        raise FileNotFoundError(f"CSV 文件不存在: {csv_file}")

    if csv_path:
        path = Path(csv_path)
        if not path.is_absolute() and HAS_FOLDER_PATHS:
            candidate = Path(folder_paths.get_input_directory()) / path
            if candidate.exists():
                path = candidate
        if not path.exists():
            raise FileNotFoundError(f"CSV 文件不存在: {path}")
        return path

    raise ValueError("请选择 CSV 文件或填写 CSV 路径")


def _resolve_excel_path(excel_file: str, excel_path: str) -> Path:
    excel_file = str(excel_file or "").strip()
    excel_path = str(excel_path or "").strip()

    if excel_file:
        if not HAS_FOLDER_PATHS:
            raise RuntimeError("folder_paths 不可用，请使用 excel_path")
        input_dir = Path(folder_paths.get_input_directory())
        direct = input_dir / excel_file
        if direct.exists():
            return direct
        filename = Path(excel_file).name
        for path in input_dir.rglob(filename):
            if path.is_file() and path.suffix.lower() == ".xlsx":
                return path
        raise FileNotFoundError(f"Excel 文件不存在: {excel_file}")

    if excel_path:
        path = Path(excel_path)
        if not path.is_absolute() and HAS_FOLDER_PATHS:
            candidate = Path(folder_paths.get_input_directory()) / path
            if candidate.exists():
                path = candidate
        if not path.exists():
            raise FileNotFoundError(f"Excel 文件不存在: {path}")
        return path

    raise ValueError("请选择 Excel 文件或填写 Excel 路径")


def _column_index(ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", ref.upper())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(ord("A") + rem) + name
    return name


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for si in root.findall("m:si", ns):
        text = "".join(t.text or "" for t in si.findall(".//m:t", ns))
        strings.append(text)
    return strings


def _cell_text(cell: ET.Element, shared_strings: list) -> str:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//m:t", ns)).strip()
    value = cell.find("m:v", ns)
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)].strip()
        except Exception:
            return ""
    return str(raw).strip()


def _read_excel_records(path: Path) -> tuple[list, list]:
    with zipfile.ZipFile(path) as zf:
        shared_strings = _xlsx_shared_strings(zf)
        root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    table = []
    for row in root.findall(".//m:sheetData/m:row", ns):
        values = {}
        max_col = 0
        for cell in row.findall("m:c", ns):
            col = _column_index(cell.attrib.get("r", ""))
            if not col:
                continue
            values[col] = _cell_text(cell, shared_strings)
            max_col = max(max_col, col)
        table.append([values.get(i, "") for i in range(1, max_col + 1)])

    if not table:
        raise ValueError("Excel 文件为空")
    headers = [str(v).strip() for v in table[0]]
    rows = []
    for row_number, values in enumerate(table[1:], start=2):
        if not any(values):
            continue
        row = {"_row_number": row_number}
        for index, header in enumerate(headers):
            if header:
                row[header] = values[index].strip() if index < len(values) else ""
        rows.append(row)
    if not rows:
        raise ValueError("Excel 文件没有有效任务")
    return headers, rows


def _read_text_excel(path: Path) -> list:
    headers, records = _read_excel_records(path)
    prompt_key = next((h for h in headers if h in ("提示词", "prompt")), None)
    size_key = next((h for h in headers if h in ("尺寸", "size")), None)
    if prompt_key is None or size_key is None:
        raise ValueError("Excel 表头必须包含：提示词、尺寸")

    rows = []
    for record in records:
        rows.append({
            "_row_number": record["_row_number"],
            "提示词": str(record.get(prompt_key) or "").strip(),
            "尺寸": str(record.get(size_key) or "").strip(),
        })
    return rows


def _inline_cell(ref: str, value) -> str:
    text = escape("" if value is None else str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _write_simple_xlsx(path: Path, headers: list, rows: list) -> None:
    sheet_rows = []
    all_rows = [headers] + rows
    for row_idx, row_values in enumerate(all_rows, start=1):
        cells = [
            _inline_cell(f"{_column_name(col_idx)}{row_idx}", value)
            for col_idx, value in enumerate(row_values, start=1)
        ]
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    dimension = f"A1:{_column_name(len(headers))}{len(all_rows)}"
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        "xl/styles.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs></styleSheet>""",
        "xl/worksheets/sheet1.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="{dimension}"/><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>""",
        "docProps/core.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"><dc:creator>ComfyUI_KuAi_Power</dc:creator><dcterms:created>{now}</dcterms:created><dcterms:modified>{now}</dcterms:modified></cp:coreProperties>""",
        "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>ComfyUI_KuAi_Power</Application></Properties>""",
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)


def _result_excel_path(source: Path) -> Path:
    result = source.with_name(f"{source.stem}_结果.xlsx")
    if not result.exists():
        return result
    for index in range(1, 1000):
        result = source.with_name(f"{source.stem}_结果_{index}.xlsx")
        if not result.exists():
            return result
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return source.with_name(f"{source.stem}_结果_{stamp}.xlsx")


def _text_result_path(source: Path) -> Path:
    return _result_excel_path(source)


def _read_csv(path: Path) -> tuple[list, list]:
    last_error = None
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    raise ValueError("CSV 文件为空或缺少表头")
                rows = []
                for row_number, row in enumerate(reader, start=2):
                    if not any(row.values()):
                        continue
                    cleaned = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                    cleaned["_row_number"] = row_number
                    rows.append(cleaned)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise RuntimeError(f"CSV 编码无法识别，请另存为 UTF-8 或 GBK: {last_error}")
    if not rows:
        raise ValueError("CSV 文件没有有效任务")
    return reader.fieldnames, rows


def _write_result_csv(path: Path, fieldnames: list, rows: list) -> None:
    output_fields = [name for name in fieldnames if name != "_row_number"]
    for name in RESULT_COLUMNS:
        if name not in output_fields:
            output_fields.append(name)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: v for k, v in row.items() if k != "_row_number"})


def _download_image(url: str, save_dir: str, prefix: str, image_index: int, timeout: int) -> tuple[str, str]:
    root = _comfy_root()
    out_dir = root / save_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if url.startswith("data:"):
        import base64
        header, b64 = url.split(",", 1)
        content = base64.b64decode(b64)
        ext = "png"
        digest_source = b64[:128]
    else:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        content = resp.content
        content_type = resp.headers.get("content-type", "").lower()
        if "jpeg" in content_type or "jpg" in content_type:
            ext = "jpg"
        elif "webp" in content_type:
            ext = "webp"
        else:
            ext = "png"
        digest_source = url

    digest = hashlib.md5(digest_source.encode("utf-8", errors="ignore")).hexdigest()[:8]
    filename = f"{prefix}_{image_index}_{digest}.{ext}"
    filepath = out_dir / filename
    filepath.write_bytes(content)
    return str(filepath.relative_to(root)), filename


def _error_text(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error") or data
            if isinstance(err, dict):
                return str(err.get("message") or err.get("detail") or err)
        return str(data)
    except Exception:
        return resp.text[:1000]


def _is_public_error(error: Exception) -> bool:
    return "PUBLIC ERROR" in str(error).upper()


def _is_retryable(error: Exception) -> bool:
    if _is_public_error(error):
        return False
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return error.response.status_code in RETRY_STATUS_CODES
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return True
    text = str(error).lower()
    return any(flag in text for flag in ["timeout", "timed out", "connection", "429", "503", "502", "504", "负载", "繁忙"])


def _post_generation(payload: dict, api_key: str, api_base: str, timeout: int) -> list:
    resp = requests.post(
        f"{api_base.rstrip('/')}/v1/images/generations",
        json=payload,
        headers=http_headers_auth_only(api_key),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        message = _error_text(resp)
        err = requests.HTTPError(message)
        err.response = resp
        raise err
    return _extract_urls(resp.json())


def _process_one(row_index: int, row: dict, defaults: dict) -> dict:
    output = dict(row)
    output.update({name: "" for name in RESULT_COLUMNS})
    prompt = str(row.get("prompt") or "").strip()
    if not prompt:
        output["status"] = "失败"
        output["error_reason"] = "prompt 不能为空"
        return output

    model = str(row.get("model") or "").strip()
    size = str(row.get("size") or "").strip()
    n_raw = str(row.get("n") or "").strip()
    missing = [name for name, value in (("model", model), ("size", size), ("n", n_raw)) if not value]
    if missing:
        output["status"] = "失败"
        output["error_reason"] = f"CSV 缺少必填参数: {', '.join(missing)}"
        return output
    api_base = defaults["api_base"]
    timeout = int(str(row.get("timeout") or defaults["request_timeout"]).strip())
    output_prefix = str(row.get("output_prefix") or f"gpt_image2_{row_index}").strip() or f"gpt_image2_{row_index}"

    try:
        n = max(1, min(10, int(n_raw)))
    except ValueError:
        output["status"] = "失败"
        output["error_reason"] = f"n 不是有效数字: {n_raw}"
        return output

    payload = {"model": model, "prompt": prompt, "n": n, "size": SIZE_MAP.get(size, size)}
    attempts = defaults["retry_count"] + 1
    last_error = ""

    for attempt in range(1, attempts + 1):
        try:
            urls = _post_generation(payload, defaults["api_key"], api_base, timeout)
            local_paths = []
            file_names = []
            for image_index, url in enumerate(urls, start=1):
                local_path, filename = _download_image(
                    url,
                    defaults["save_dir"],
                    output_prefix,
                    image_index,
                    defaults["download_timeout"],
                )
                local_paths.append(local_path)
                file_names.append(filename)

            output["status"] = "成功"
            output["image_urls"] = "\n".join(urls)
            output["local_paths"] = "\n".join(local_paths)
            output["file_names"] = "\n".join(file_names)
            return output
        except Exception as exc:
            last_error = str(exc)
            if attempt >= attempts or not _is_retryable(exc):
                break
            time.sleep(defaults["retry_interval"])

    output["status"] = "失败"
    output["error_reason"] = last_error
    return output


def _process_text_excel_row(row_index: int, row: dict, defaults: dict) -> dict:
    prompt = str(row.get("提示词") or "").strip()
    size = str(row.get("尺寸") or "").strip()
    output = {
        "_row_number": row.get("_row_number", row_index),
        "提示词": prompt,
        "尺寸": size,
        "状态": "",
        "失败原因": "",
        "保存路径": "",
        "文件名": "",
    }
    if not prompt:
        output["状态"] = "失败"
        output["失败原因"] = "提示词不能为空"
        return output
    if not size:
        output["状态"] = "失败"
        output["失败原因"] = "尺寸不能为空"
        return output

    payload = {"model": "gpt-image-2", "prompt": prompt, "n": 1, "size": SIZE_MAP.get(size, size)}
    attempts = defaults["retry_count"] + 1
    output_prefix = f"gpt_image2_{row_index}"
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            urls = _post_generation(
                payload,
                defaults["api_key"],
                defaults["api_base"],
                defaults["request_timeout"],
            )
            local_path, filename = _download_image(
                urls[0],
                defaults["save_dir"],
                output_prefix,
                1,
                defaults["download_timeout"],
            )
            output["状态"] = "成功"
            output["保存路径"] = local_path
            output["文件名"] = filename
            return output
        except Exception as exc:
            last_error = str(exc)
            if attempt >= attempts or not _is_retryable(exc):
                break
            time.sleep(defaults["retry_interval"])

    output["状态"] = "失败"
    output["失败原因"] = last_error
    return output


class GPTImage2BatchTextGenerate:
    """GPT Image 2 Excel batch text-to-image node."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "excel_file": (_input_excel_files(), {
                    "tooltip": "上传或选择 input 目录中的 Excel",
                    "image_upload": True,
                    "editable": True,
                }),
                "excel_path": ("STRING", {"default": "", "tooltip": "Excel 完整路径"}),
                "api_key": ("STRING", {"default": "", "tooltip": "留空使用 KUAI_API_KEY"}),
                "api_base": ("STRING", {"default": "https://ai.kegeai.top"}),
                "save_dir": ("STRING", {"default": "output/gpt_image2_batch"}),
                "batch_size": ("INT", {"default": 10, "min": 1, "max": 20}),
                "request_timeout": ("INT", {"default": 1800, "min": 30, "max": 9999}),
                "download_timeout": ("INT", {"default": 1800, "min": 30, "max": 9999}),
                "retry_count": ("INT", {"default": 3, "min": 0, "max": 10}),
                "retry_interval": ("INT", {"default": 3, "min": 0, "max": 120}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "excel_file": "Excel文件",
            "excel_path": "Excel路径",
            "api_key": "API密钥",
            "api_base": "API地址",
            "save_dir": "图片保存目录",
            "batch_size": "并发数",
            "request_timeout": "请求超时",
            "download_timeout": "下载超时",
            "retry_count": "重试次数",
            "retry_interval": "重试间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("处理报告", "结果Excel路径", "图片保存目录", "成功数量", "失败数量")
    FUNCTION = "process"
    CATEGORY = "KuAi/GPTImage"
    OUTPUT_NODE = True

    def process(self, excel_file="", excel_path="", api_key="", api_base="https://ai.kegeai.top",
                save_dir="output/gpt_image2_batch", batch_size=10, request_timeout=1800,
                download_timeout=1800, retry_count=3, retry_interval=3):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请填写 api_key 或设置 KUAI_API_KEY")

        source = _resolve_excel_path(excel_file, excel_path)
        rows = _read_text_excel(source)
        total = len(rows)
        defaults = {
            "api_key": api_key,
            "api_base": api_base,
            "save_dir": save_dir,
            "request_timeout": request_timeout,
            "download_timeout": download_timeout,
            "retry_count": retry_count,
            "retry_interval": retry_interval,
        }

        print(f"[GPTImage2Batch] 开始处理 {total} 条任务，并发数 {batch_size}")
        results = []
        for batch_start in range(0, total, batch_size):
            batch = rows[batch_start: batch_start + batch_size]
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as executor:
                future_map = {
                    executor.submit(_process_text_excel_row, batch_start + local_i + 1, row, defaults): batch_start + local_i + 1
                    for local_i, row in enumerate(batch)
                }
                for future in concurrent.futures.as_completed(future_map):
                    results.append(future.result())

        results.sort(key=lambda item: item.get("_row_number", 0))
        result_path = _text_result_path(source)
        _write_simple_xlsx(
            result_path,
            TEXT_EXCEL_RESULT_HEADERS,
            [[row.get(header, "") for header in TEXT_EXCEL_RESULT_HEADERS] for row in results],
        )

        success = [row for row in results if row.get("状态") == "成功"]
        failed = [row for row in results if row.get("状态") != "成功"]
        abs_save_dir = str(_comfy_root() / save_dir)
        lines = [
            "GPT-Image2批量文生图完成",
            f"总计: {total}",
            f"成功: {len(success)}",
            f"失败: {len(failed)}",
            f"结果Excel: {result_path}",
            f"图片目录: {abs_save_dir}",
        ]
        if failed:
            lines.append("失败记录:")
            for row in failed:
                lines.append(f"行 {row.get('_row_number', '')}: {row.get('失败原因', '')}")
        report = "\n".join(lines)
        print(report)
        return (report, str(result_path), abs_save_dir, len(success), len(failed))


NODE_CLASS_MAPPINGS = {
    "GPTImage2BatchTextGenerate": GPTImage2BatchTextGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GPTImage2BatchTextGenerate": "🖼️ GPT-Image2批量文生图",
}
