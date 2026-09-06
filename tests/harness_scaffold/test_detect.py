import json

import scripts.harness_scaffold as hs


def test_detect_state_greenfield(tmp_path):
    (tmp_path / "README.md").write_text("# hi", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert hs.detect_state(tmp_path) == "greenfield"


def test_detect_state_brownfield_when_source_present(tmp_path):
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    assert hs.detect_state(tmp_path) == "brownfield"


def test_detect_state_ignores_vendored_dirs(tmp_path):
    nm = tmp_path / "node_modules" / "x"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("//x", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi", encoding="utf-8")
    assert hs.detect_state(tmp_path) == "greenfield"


def test_detect_frameworks_package_json(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"next": "15.0.1", "react": "19.0.0"}}),
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("next.js") == "15.0.1"


def test_detect_frameworks_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["fastapi==0.118.0", "uvicorn"]\n', encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("fastapi") == "0.118.0"


def test_detect_frameworks_pyproject_poetry(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry.dependencies]\nfastapi = "^0.118.0"\ndjango = "^5.0"\n',
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("fastapi") == "0.118.0"
    assert found.get("django") == "5.0"


def test_detect_frameworks_requirements_txt(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "# comment\nflask==3.0.0\nrequests>=2.0\n", encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("flask") == "3.0.0"


def test_detect_frameworks_requirements_dedup_with_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["flask==3.0.0"]\n', encoding="utf-8"
    )
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert names.count("flask") == 1  # dedup by name even across two manifests


def test_detect_frameworks_dedup_same_label(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {"dependencies": {"nestjs": "10.0.0", "@nestjs/core": "10.0.0", "next": "15.0.1"}}
        ),
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert names.count("nestjs") == 1
    assert len(names) == len(set(names))


def test_detect_frameworks_csproj_aspnetcore(tmp_path):
    (tmp_path / "App.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk.Web">\n'
        "  <PropertyGroup>\n"
        "    <TargetFramework>net8.0</TargetFramework>\n"
        "  </PropertyGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "aspnet-core" in names


def test_detect_frameworks_csproj_wpf_property(tmp_path):
    (tmp_path / "App.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        "  <PropertyGroup>\n"
        "    <UseWPF>true</UseWPF>\n"
        "  </PropertyGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "wpf" in names


def test_detect_frameworks_csproj_package_reference(tmp_path):
    (tmp_path / "App.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        "  <ItemGroup>\n"
        '    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />\n'
        "  </ItemGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("entity-framework-core") == "8.0.0"


def test_detect_frameworks_pom_xml(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project>\n"
        "  <dependencies>\n"
        "    <dependency>\n"
        "      <groupId>org.springframework.boot</groupId>\n"
        "      <artifactId>spring-boot-starter-web</artifactId>\n"
        "      <version>3.2.0</version>\n"
        "    </dependency>\n"
        "  </dependencies>\n"
        "</project>\n",
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("spring-boot") == "3.2.0"


def test_detect_frameworks_gradle_kts(tmp_path):
    (tmp_path / "build.gradle.kts").write_text(
        "dependencies {\n"
        '    implementation("org.springframework.boot:spring-boot-starter-web:3.2.0")\n'
        "}\n",
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("spring-boot") == "3.2.0"


def test_detect_frameworks_gradle_kotlin_ktor(tmp_path):
    (tmp_path / "build.gradle.kts").write_text(
        'implementation("io.ktor:ktor-server-core:2.3.0")\n', encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("ktor") == "2.3.0"


def test_detect_frameworks_cmake(tmp_path):
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\nproject(myapp)\n", encoding="utf-8"
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "cmake" in names


def test_detect_frameworks_vcpkg(tmp_path):
    (tmp_path / "vcpkg.json").write_text(
        json.dumps({"name": "myapp", "dependencies": ["boost", "fmt"]}), encoding="utf-8"
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "boost" in names
    assert "fmt" in names


def test_detect_frameworks_conanfile_txt(tmp_path):
    (tmp_path / "conanfile.txt").write_text(
        "[requires]\nfmt/10.1.1\nspdlog/1.12.0\n\n[generators]\nCMakeDeps\n", encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("fmt") == "10.1.1"
    assert found.get("spdlog") == "1.12.0"


def test_detect_frameworks_conanfile_py(tmp_path):
    (tmp_path / "conanfile.py").write_text(
        "from conan import ConanFile\n\n\nclass Pkg(ConanFile):\n"
        '    def requirements(self):\n        self.requires("boost/1.83.0")\n',
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "boost" in names


def test_detect_frameworks_cargo_toml(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "myapp"\nversion = "0.1.0"\n\n'
        '[dependencies]\naxum = "0.7.4"\ntokio = { version = "1", features = ["full"] }\n',
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("axum") == "0.7.4"
    assert found.get("tokio") == "1"


def test_detect_frameworks_composer_json(tmp_path):
    (tmp_path / "composer.json").write_text(
        json.dumps({"require": {"laravel/framework": "^10.0"}}), encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("laravel") == "10.0"


def test_detect_frameworks_gemfile(tmp_path):
    (tmp_path / "Gemfile").write_text(
        'source "https://rubygems.org"\ngem "rails", "~> 7.1.0"\n', encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("rails") == "7.1.0"


def test_detect_frameworks_package_swift(tmp_path):
    (tmp_path / "Package.swift").write_text(
        "// swift-tools-version:5.9\n"
        "import PackageDescription\n\n"
        "let package = Package(\n"
        "  dependencies: [\n"
        '    .package(url: "https://github.com/vapor/vapor.git", from: "4.0.0")\n'
        "  ]\n"
        ")\n",
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "vapor" in names


def test_detect_frameworks_xcodeproj_marker(tmp_path):
    (tmp_path / "MyApp.xcodeproj").mkdir()
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "xcode" in names


def test_detect_frameworks_build_sbt(tmp_path):
    (tmp_path / "build.sbt").write_text(
        'libraryDependencies += "org.playframework" %% "play" % "3.0.0"\n', encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("play-framework") == "3.0.0"
