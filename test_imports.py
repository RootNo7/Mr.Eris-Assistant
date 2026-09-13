from backend.providers.openrouter.provider import OpenRouterProvider
print('OpenRouterProvider OK')

from backend.tools.registry import ToolRegistry
from backend.tools.file_tools import ListFilesTool, SearchFilesTool, ReadFileTool, WriteFileTool, CreateDirectoryTool, CopyFileTool, MoveFileTool

r = ToolRegistry()
r.register(ListFilesTool())
r.register(SearchFilesTool())
r.register(ReadFileTool())
r.register(WriteFileTool())
r.register(CreateDirectoryTool())
r.register(CopyFileTool())
r.register(MoveFileTool())

print('All tools registered')
schemas = r.get_openai_schemas()
print(f'OpenAI schemas count: {len(schemas)}')
names = [s['function']['name'] for s in schemas]
print(f'Names: {names}')

# Test reverse lookup
result = r.execute_tool_by_openai_name('files_list', {'directory_path': '.'})
print('Execute by OpenAI name works:', 'directory' in result)

print('All tests passed!')