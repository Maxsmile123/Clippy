# Конфиг задачи

У каждой задачи есть собственный конфигурационный файл: `task.json`

## Поля

| Поле | Значение                                                                         |
| --- |----------------------------------------------------------------------------------|
| `tests` | группы тестов                                                                    |
| `lint_files` | Файлы / директории, к которым будут применяться линтеры                          |
| `submit_files` | Файлы / директории, которые будут отправлены на проверку                         |
| `forbidden` | Список паттернов (подстрок / регулярных выражений), запрещенных в файлах решения |
