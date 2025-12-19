import xml.etree.ElementTree as ET

# JaCoCo 插件配置片段
JACOCO_PLUGIN = """
<plugin>
    <groupId>org.jacoco</groupId>
    <artifactId>jacoco-maven-plugin</artifactId>
    <version>0.8.10</version>
    <executions>
        <execution>
            <goals>
                <goal>prepare-agent</goal>
            </goals>
        </execution>
        <execution>
            <id>report</id>
            <phase>test</phase>
            <goals>
                <goal>report</goal>
            </goals>
        </execution>
    </executions>
</plugin>
"""

def inject_jacoco_into_pom(pom_path):
    print(f"💉 Injecting JaCoCo into {pom_path}...")
    
    # 注册 Maven 命名空间，防止修改后 xmlns 乱掉
    ET.register_namespace('', "http://maven.apache.org/POM/4.0.0")
    tree = ET.parse(pom_path)
    root = tree.getroot()
    
    ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
    
    # 1. 找到 <build> 标签，没有就创建
    build = root.find('mvn:build', ns)
    if build is None:
        build = ET.SubElement(root, 'build')
    
    # 2. 找到 <plugins> 标签，没有就创建
    plugins = build.find('mvn:plugins', ns)
    if plugins is None:
        plugins = ET.SubElement(build, 'plugins')
        
    # 3. 检查是否已经存在 JaCoCo，防止重复添加
    jacoco_exists = False
    for p in plugins.findall('mvn:plugin', ns):
        aid = p.find('mvn:artifactId', ns)
        if aid is not None and "jacoco" in aid.text:
            print("   ⚠️ JaCoCo plugin already exists. Skipping plugin injection.")
            jacoco_exists = True
            break

    # 4. 插入插件 (如果不存在)
    if not jacoco_exists:
        plugin_element = ET.fromstring(JACOCO_PLUGIN)
        plugins.append(plugin_element)

    # 5. 注入 maven-surefire-plugin.argLine 属性，确保 JaCoCo agent 被包含
    properties = root.find('mvn:properties', ns)
    if properties is None:
        properties = ET.SubElement(root, 'properties')
    
    arg_line_prop = properties.find('mvn:maven-surefire-plugin.argLine', ns)
    if arg_line_prop is None:
        # 如果属性不存在，创建一个新的，值为 @{argLine}
        arg_line_prop = ET.SubElement(properties, 'maven-surefire-plugin.argLine')
        arg_line_prop.text = "@{argLine}"
        print("   ✅ Added maven-surefire-plugin.argLine property.")
    else:
        # 如果属性存在，追加 @{argLine} (如果还没有的话)
        if arg_line_prop.text and "@{argLine}" not in arg_line_prop.text:
            arg_line_prop.text = f"{arg_line_prop.text} @{{argLine}}"
            print("   ✅ Appended @{argLine} to existing maven-surefire-plugin.argLine.")
        elif not arg_line_prop.text:
             arg_line_prop.text = "@{argLine}"
             print("   ✅ Set empty maven-surefire-plugin.argLine to @{argLine}.")

    # 6. 保存文件
    tree.write(pom_path, encoding='utf-8', xml_declaration=True)
    print("   ✅ JaCoCo injected successfully.")

if __name__ == "__main__":
    import sys
    target_pom = sys.argv[1] if len(sys.argv) > 1 else "pom.xml"
    inject_jacoco_into_pom(target_pom)