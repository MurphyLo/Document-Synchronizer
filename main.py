from doc_maintainer import DocMaintainer

async def main():
    maintainer = DocMaintainer()
    await maintainer.run("开始文档同步")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
