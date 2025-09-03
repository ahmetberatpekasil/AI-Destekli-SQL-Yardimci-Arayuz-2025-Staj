import os, sys, json, re, psycopg2
from contextlib import contextmanager
from dotenv import load_dotenv
from google import genai
from google.genai import types
from psycopg2 import sql
from psycopg2.extras import RealDictCursor 

load_dotenv()

# DB bağlantısı
db_connection = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    port=os.getenv("DB_PORT"),
)

# Güvenli cursor + JSON-dostu dönüşüm
@contextmanager
def db_cursor():
    cursor = None
    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        yield cursor
        db_connection.commit()
    except psycopg2.Error:
        if db_connection:
            db_connection.rollback()
        raise
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass

def rows_as_dicts(cursor):
    return list(cursor.fetchall())

# Yardımcılar
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# DDL allow-list: kolon tipi/kısıtı sadece güvenli karakterlerden oluşmalı
_TYPE_RE = re.compile(r"^[A-Z0-9_(),\s]+$")

def _ident(name: str) -> sql.Identifier:
    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Geçersiz isim: {name}")
    return sql.Identifier(name)

def _parse(content):
    """
    content JSON string beklenir; ancak dict/list gelirse doğrudan kabul edilir.
    """
    if content is None or content == "":
        raise ValueError("content boş. JSON string bekleniyor.")
    if isinstance(content, (dict, list)):
        return content
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("content bir JSON obje olmalı.")
    return data

def _build_where_simple(where: dict):
    """dict -> (WHERE sql.SQL, params list). Tek değer '=', liste/tuple 'IN (...)', None -> IS NULL."""
    if not where:
        return sql.SQL(""), []
    clauses, params = [], []
    for key, val in where.items():
        col = _ident(key)
        if val is None:
            clauses.append(sql.SQL("{} IS NULL").format(col))
        elif isinstance(val, (list, tuple)):
            if not val:
                clauses.append(sql.SQL("FALSE"))  # boş IN güvenli
            else:
                placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in val)
                clauses.append(sql.SQL("{} IN ({})").format(col, placeholders))
                params.extend(val)
        else:
            clauses.append(sql.SQL("{} = {}").format(col, sql.Placeholder()))
            params.append(val)
    return (sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses), params) if clauses else (sql.SQL(""), [])

# İşlevler 
def create_sql_table(content: str):
    """
    JSON:
    {
      "table": "person",
      "columns": {"id":"INT PRIMARY KEY","name":"VARCHAR(255)","age":"INT","gender":"CHAR(1)"},
      "if_not_exists": true
    }
    """
    data = _parse(content)
    table = data["table"]
    columns = data["columns"]
    if_not_exists = bool(data.get("if_not_exists", True))
    if not isinstance(columns, dict) or not columns:
        raise ValueError("'columns' dict olmalı ve boş olmamalı.")

    column_defs = []
    for column_name, column_type in columns.items():
        # DDL allow-list kontrolü (kolon tipi/kısıtı)
        if not isinstance(column_type, str) or not _TYPE_RE.match(column_type.upper()):
            raise ValueError(f"Geçersiz/izin verilmeyen kolon tipi/kısıtı: {column_type!r}")
        column_defs.append(sql.SQL("{} {}").format(_ident(column_name), sql.SQL(column_type)))

    query = sql.SQL("CREATE TABLE {}{} ({})").format(
        sql.SQL("IF NOT EXISTS ") if if_not_exists else sql.SQL(""),
        _ident(table),
        sql.SQL(", ").join(column_defs),
    )
    with db_cursor() as cursor:
        cursor.execute(query)
    return f"{table} tablosu oluşturuldu (ya da zaten vardı)."

def drop_sql_table(content: str):
    """
    JSON:
    {
      "table": "person",
      "if_exists": true,      # opsiyonel (default: true)
      "cascade": false        # opsiyonel
    }
    """
    data = _parse(content)
    table = data["table"]
    if_exists = bool(data.get("if_exists", True))
    cascade = bool(data.get("cascade", False))
    query = sql.SQL("DROP TABLE {}{}{}").format(
        sql.SQL("IF EXISTS ") if if_exists else sql.SQL(""),
        _ident(table),
        sql.SQL(" CASCADE") if cascade else sql.SQL(""),
    )
    with db_cursor() as cursor:
        cursor.execute(query)
    return f"{table} tablosu silindi." if if_exists else f"{table} tablosu drop komutu uygulandı."

def insert_sql_entry(content: str):
    """
    JSON: {"table":"person","values":{"id":1,"name":"Mike","age":30,"gender":"m"}}
    """
    data = _parse(content)
    table = data["table"]
    values = data["values"]
    if not isinstance(values, dict) or not values:
        raise ValueError("'values' dict olmalı ve boş olmamalı.")

    column_identifiers = [_ident(k) for k in values.keys()]
    params = list(values.values())
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in column_identifiers)

    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        _ident(table), sql.SQL(", ").join(column_identifiers), placeholders
    )
    with db_cursor() as cursor:
        cursor.execute(query, params)
        data = rows_as_dicts(cursor)
    return {"inserted": len(data), "rows": data}

def read_sql_entry(content: str):
    """
    JSON:
    {
      "table":"person",
      "columns":["id","name"],         # opsiyonel; yoksa "*"
      "where":{"name":"Bob","id":[1]}  # opsiyonel
    }
    """
    data = _parse(content)
    table = data["table"]
    columns = data.get("columns")
    col_sql = sql.SQL(", ").join(_ident(c) for c in columns) if columns else sql.SQL("*")
    where_sql, params = _build_where_simple(data.get("where", {}))
    query = sql.SQL("SELECT {} FROM {}").format(col_sql, _ident(table)) + where_sql

    limit = data.get("limit")
    if isinstance(limit, int) and limit > 0:
        query = query + sql.SQL(" LIMIT {}").format(sql.Literal(limit))

    with db_cursor() as cursor:
        cursor.execute(query, params)
        rows = rows_as_dicts(cursor)
    return {"count": len(rows), "rows": rows}

def delete_sql_entry(content: str):
    """
    JSON: {"table":"person","where":{"id":1}}  # WHERE zorunlu
    """
    data = _parse(content)
    table = data["table"]
    where = data.get("where")
    if not where:
        raise ValueError("Güvenlik için WHERE zorunludur.")

    where_sql, params = _build_where_simple(where)
    query = sql.SQL("DELETE FROM {}").format(_ident(table)) + where_sql + sql.SQL(" RETURNING *")

    with db_cursor() as cursor:
        cursor.execute(query, params)
        rows = rows_as_dicts(cursor)
    return {"deleted": len(rows), "rows": rows}

def update_sql_entry(content: str):
    """
    JSON: {"table":"person","set":{"name":"Veli"},"where":{"id":1}}
    """
    data = _parse(content)
    table = data["table"]
    set_map = data.get("set")
    where = data.get("where")

    if not isinstance(set_map, dict) or not set_map:
        raise ValueError("'set' dict olmalı ve boş olmamalı.")
    if not where:
        raise ValueError("Güvenlik için WHERE zorunludur.")

    set_clauses = []
    params = []
    for col_name, value in set_map.items():
        set_clauses.append(sql.SQL("{} = {}").format(_ident(col_name), sql.Placeholder()))
        params.append(value)

    where_sql, where_params = _build_where_simple(where)
    query = (
        sql.SQL("UPDATE {} SET ").format(_ident(table))
        + sql.SQL(", ").join(set_clauses)
        + where_sql
        + sql.SQL(" RETURNING *")
    )

    with db_cursor() as cursor:
        cursor.execute(query, params + where_params)
        rows = rows_as_dicts(cursor)
    return {"updated": len(rows), "rows": rows}

def list_tables(content: str):
    """
    JSON (opsiyonel alanlar):
      {"schema":"public","include_views":false,"pattern":"user","limit":200}
    """
    data = _parse(content)
    schema = data.get("schema")
    include_views = bool(data.get("include_views", False))
    pattern = data.get("pattern")
    limit = data.get("limit", 200)

    where_sql = [sql.SQL("1=1")]
    params = []

    if not include_views:
        where_sql.append(sql.SQL("table_type = 'BASE TABLE'"))

    if schema:
        where_sql.append(sql.SQL("table_schema = {}").format(sql.Placeholder()))
        params.append(schema)

    if pattern:
        # wildcard yoksa baş/sona % ekleyelim (ILIKE ile case-insensitive arama)
        pat = pattern if any(ch in pattern for ch in ("%","_")) else f"%{pattern}%"
        where_sql.append(sql.SQL("table_name ILIKE {}").format(sql.Placeholder()))
        params.append(pat)

    query = (
        sql.SQL("SELECT table_schema, table_name, table_type "
                "FROM information_schema.tables WHERE ")
        + sql.SQL(" AND ").join(where_sql)
        + sql.SQL(" ORDER BY table_schema, table_name")
    )
    if isinstance(limit, int) and limit > 0:
        query = query + sql.SQL(" LIMIT {}").format(sql.Literal(limit))

    with db_cursor() as cursor:
        cursor.execute(query, params)
        rows = rows_as_dicts(cursor)
    return {"count": len(rows), "tables": rows}

# LLM tool setup 
API_KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
if not API_KEY:
    print("API key bulunamadı (.env -> GEMINI_API_KEY)."); sys.exit(1)

client = genai.Client(api_key=API_KEY)
MODEL = "gemini-2.5-flash"

tools = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="create_sql_table",
        description="Create a SQL table. JSON: {\"table\":\"...\",\"columns\":{\"col\":\"TYPE ...\"},\"if_not_exists\":true}",
        parameters=types.Schema(type="OBJECT",
            properties={"content": types.Schema(type="STRING", description="JSON string")},
            required=["content"]),
    ),
    types.FunctionDeclaration(
        name="drop_sql_table",
        description="Drop a SQL table. JSON: {\"table\":\"...\",\"if_exists\":true,\"cascade\":false}",
        parameters=types.Schema(type="OBJECT",
            properties={"content": types.Schema(type="STRING", description="JSON string")},
            required=["content"]),
    ),
    types.FunctionDeclaration(
        name="insert_sql_entry",
        description="Insert a row. JSON: {\"table\":\"...\",\"values\":{\"col\":val,...}}",
        parameters=types.Schema(type="OBJECT",
            properties={"content": types.Schema(type="STRING", description="JSON string")},
            required=["content"]),
    ),
    types.FunctionDeclaration(
        name="read_sql_entry",
        description="Read rows. JSON: {\"table\":\"...\",\"columns\":[...],\"where\":{...},\"limit\":N}",
        parameters=types.Schema(type="OBJECT",
            properties={"content": types.Schema(type="STRING", description="JSON string")},
            required=["content"]),
    ),
    types.FunctionDeclaration(
        name="delete_sql_entry",
        description="Delete rows (WHERE required). JSON: {\"table\":\"...\",\"where\":{...}}",
        parameters=types.Schema(type="OBJECT",
            properties={"content": types.Schema(type="STRING", description="JSON string")},
            required=["content"]),
    ),
    types.FunctionDeclaration(
        name="update_sql_entry",
        description="Update rows (WHERE required). JSON: {\"table\":\"...\",\"set\":{...},\"where\":{...}}",
        parameters=types.Schema(type="OBJECT",
            properties={"content": types.Schema(type="STRING", description="JSON string")},
            required=["content"]),
    ),
    types.FunctionDeclaration(
        name="list_tables",
        description="List tables. JSON: {\"schema\":\"public\",\"include_views\":false,\"pattern\":\"user\",\"limit\":200}",
        parameters=types.Schema(type="OBJECT",
            properties={"content": types.Schema(type="STRING", description="JSON string")},
            required=["content"]),
    ),
])

GEN_CONFIG = types.GenerateContentConfig(
    tools=[tools],
    temperature=0.25,
    system_instruction=(
        # Kimlik
        "Genel amaçlı bir Türkçe asistansın. Kullanıcı günlük konularda da soru sorabilir, "
        "SQL/veritabanı işlemleri de isteyebilir. Yanıtlarında sakin, net ve kısa ol; "
        "kullanıcı 'detaylı', 'adım adım', 'uzun anlat' derse kapsamı genişlet. "
        "'kısaca', 'özetle' derse 3–5 cümleyi aşma.\n"
        "\n"
        # Çıktı stili
        "- Günlük sorularda: gerekirse maddelerle, kısa örnek/verim odaklı yanıt ver.\n"
        "- Teknik yanıtlarda: mümkün oldukça kesin ifade kullan; gereksiz süsleme yapma.\n"
        "\n"
        # SQL niyet tespiti ve araçlar
        "Kullanıcı SQL niyeti taşıyorsa uygun aracı çağır. İçerik numunesi: tablo/kolon isimleri, "
        "filtreler, değerler. Araç çağrıları her zaman `content` içinde **JSON string** ile yapılır "
        "(eğer JSON obje verilmişse string’e çevir). WHERE sade mod: tek değer (=), liste/tuple (IN), None (IS NULL).\n"
        "\n"
        "EŞANLAMLILAR / TETİKLEYİCİLER -> FONKSİYON HARİTASI:\n"
        "- 'tablo oluştur', 'create table', 'yeni tablo', 'schema oluştur' -> create_sql_table\n"
        "- 'tablo sil', 'drop table', 'kaldır tablo' -> drop_sql_table\n"
        "- 'ekle', 'insert', 'kayıt ekle', 'satır ekle' -> insert_sql_entry\n"
        "- 'oku', 'select', 'getir', 'listele', 'sorgula' -> read_sql_entry\n"
        "- 'sil', 'delete', 'satır sil', 'kayıt sil' -> delete_sql_entry (WHERE zorunlu)\n"
        "- 'güncelle', 'update', 'set et' -> update_sql_entry (WHERE zorunlu)\n"
        "- 'tablolar', 'tabloları listele', 'list tables', 'schema listesi' -> list_tables\n"
        "\n"
        # Örnekler
        "• 'person'ı güncelle (id=1, name=Veli) -> {\"table\":\"person\",\"set\":{\"name\":\"Veli\"},\"where\":{\"id\":1}}\n"
        "• 'public şemasındaki tabloları listele' -> {\"schema\":\"public\",\"include_views\":false}\n"
        "\n"
        # Güvenlik
        "Tablo/kolon adları yalnızca geçerli tanımlayıcılar olmalı; kolon tipleri güvenli karakterlerden oluşmalı. "
        "Okuma işlemlerinde makul limitler kullan (varsayılan 100; kullanıcı belirtirse onu uygula). "
        "Anlaşılmayan eksik bilgi varsa KISA netleştirme sorusu sor.\n"
    ),
)

def extract_text_parts(response) -> str:
    texts = []
    if not (hasattr(response, "candidates") and response.candidates):
        return ""
    for candidate in response.candidates:
        content = getattr(candidate, "content", None)
        if not content or not (hasattr(content, "parts") and content.parts):
            continue
        for part in content.parts:
            if hasattr(part, "text") and part.text:
                texts.append(part.text)
    return "\n".join(texts).strip()

def extract_function_call(response):
    if hasattr(response, "function_calls") and response.function_calls:
        return response.function_calls[0]
    if hasattr(response, "candidates") and response.candidates:
        for candidate in response.candidates:
            content = getattr(candidate, "content", None)
            if not content or not (hasattr(content, "parts") and content.parts):
                continue
            for part in content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    return part.function_call
    return None

def handle_user_message(user_text: str) -> str:
    first = client.models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=user_text)])],
        config=GEN_CONFIG,
    )

    function_call = extract_function_call(first)
    if not function_call:
        return extract_text_parts(first) or "Boş yanıt."

    args = function_call.args if isinstance(function_call.args, dict) else dict(function_call.args)
    name = (function_call.name or "").strip()

    try:
        if name == "create_sql_table":
            result = create_sql_table(args.get("content"))
            tool_result = {"ok": True, "message": f"Tablo oluşturma sonucu: {result}"}
        elif name == "drop_sql_table":
            result = drop_sql_table(args.get("content"))
            tool_result = {"ok": True, "message": result}
        elif name == "insert_sql_entry":
            created = insert_sql_entry(args.get("content"))
            tool_result = {"ok": True, "message": "Oluşturuldu", "data": created}
        elif name == "read_sql_entry":
            read = read_sql_entry(args.get("content"))
            tool_result = {"ok": True, "message": "Bilgiler", "data": read}
        elif name == "delete_sql_entry":
            deleted = delete_sql_entry(args.get("content"))
            tool_result = {"ok": True, "message": "Silindi", "data": deleted}
        elif name == "update_sql_entry":
            updated = update_sql_entry(args.get("content"))
            tool_result = {"ok": True, "message": "Güncellendi", "data": updated}
        elif name == "list_tables":
            lst = list_tables(args.get("content"))
            tool_result = {"ok": True, "message": "Tablolar", "data": lst}
        else:
            tool_result = {"ok": False, "error": f"Bilinmeyen tool: {name}"}
    except Exception as exc:
        tool_result = {"ok": False, "error": str(exc)}

    tool_part = types.Part.from_function_response(name=name, response=tool_result)
    second = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Content(role="user", parts=[types.Part.from_text(text=user_text)]),
            first.candidates[0].content,
            types.Content(role="tool", parts=[tool_part]),
        ],
        config=GEN_CONFIG,
    )
    return extract_text_parts(second) or tool_result.get("message", str(tool_result))

if __name__ == "__main__":
    print("Sohbet açık. Çıkış için '.' yazın.")
    try:
        while True:
            user_input = input("Siz: ").strip()
            if user_input == ".":
                print("Görüşürüz!")
                break
            if not user_input:
                continue
            print("Asistan:", handle_user_message(user_input))
    except KeyboardInterrupt:
        print("\nİptal edildi.")
    finally:
        try:
            db_connection.close()
        except Exception:
            pass
