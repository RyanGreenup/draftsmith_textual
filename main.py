import typer


def main(api_scheme: str = "http", api_host: str = "localhost", api_port: int = 37240):
    base_url = f"{api_scheme}://{api_host}:{api_port}"
    print(f"Accessing API at {base_url}")


if __name__ == "__main__":
    typer.run(main)

