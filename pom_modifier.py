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
    jacoco_plugin = None
    for p in plugins.findall('mvn:plugin', ns):
        aid = p.find('mvn:artifactId', ns)
        if aid is not None and "jacoco" in aid.text:
            print("   ⚠️ JaCoCo plugin already exists. Checking executions...")
            jacoco_plugin = p
            break

    # 4. 插入插件 (如果不存在) 或 补充 Executions (如果存在但缺失)
    if jacoco_plugin is None:
        plugin_element = ET.fromstring(JACOCO_PLUGIN)
        plugins.append(plugin_element)
        print("   ✅ Injected new JaCoCo plugin.")
    else:
        # 检查是否有 executions
        executions = jacoco_plugin.find('mvn:executions', ns)
        if executions is None:
            executions = ET.SubElement(jacoco_plugin, 'executions')
        
        # 简单的检查：如果 executions 为空或者看起来不完整，我们直接追加我们的标准 executions
        # 这里我们直接把标准配置里的 execution 节点复制过去
        # 为了避免重复，我们先检查有没有 prepare-agent 和 report
        has_prepare = False
        has_report = False
        for exe in executions.findall('mvn:execution', ns):
            goals = exe.find('mvn:goals', ns)
            if goals is not None:
                for goal in goals.findall('mvn:goal', ns):
                    if goal.text == 'prepare-agent': has_prepare = True
                    if goal.text == 'report': has_report = True
        
        target_plugin = ET.fromstring(JACOCO_PLUGIN)
        target_executions = target_plugin.find('executions')
        
        if not has_prepare:
            print("   ➕ Adding missing 'prepare-agent' execution.")
            # 找到 target 中的 prepare-agent execution
            for exe in target_executions:
                goals = exe.find('goals')
                if goals is not None and any(g.text == 'prepare-agent' for g in goals):
                    executions.append(exe)
                    break
                    
        if not has_report:
            print("   ➕ Adding missing 'report' execution.")
            # 找到 target 中的 report execution
            for exe in target_executions:
                goals = exe.find('goals')
                if goals is not None and any(g.text == 'report' for g in goals):
                    executions.append(exe)
                    break

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

    # 6. 强制修改 maven-surefire-plugin 的配置 (包括 pluginManagement)
    # 查找所有 plugins 列表 (build/plugins 和 build/pluginManagement/plugins)
    plugin_lists = []
    if build.find('mvn:plugins', ns) is not None:
        plugin_lists.append(build.find('mvn:plugins', ns))
    
    plugin_mgmt = build.find('mvn:pluginManagement', ns)
    if plugin_mgmt is not None:
        mgmt_plugins = plugin_mgmt.find('mvn:plugins', ns)
        if mgmt_plugins is not None:
            plugin_lists.append(mgmt_plugins)

    for p_list in plugin_lists:
        for p in p_list.findall('mvn:plugin', ns):
            aid = p.find('mvn:artifactId', ns)
            if aid is not None and "maven-surefire-plugin" in aid.text:
                config = p.find('mvn:configuration', ns)
                if config is None:
                    config = ET.SubElement(p, 'configuration')
                
                argLine = config.find('mvn:argLine', ns)
                if argLine is None:
                    argLine = ET.SubElement(config, 'argLine')
                    argLine.text = "@{argLine}"
                    print(f"   ✅ Added argLine to surefire plugin in {p_list.tag}.")
                else:
                    if argLine.text and "@{argLine}" not in argLine.text:
                        argLine.text = f"{argLine.text} @{{argLine}}"
                        print(f"   ✅ Appended @{{argLine}} to surefire argLine in {p_list.tag}.")
                    elif not argLine.text:
                        argLine.text = "@{argLine}"

    # 7. 保存文件
    tree.write(pom_path, encoding='utf-8', xml_declaration=True)
    print("   ✅ JaCoCo injected successfully.")

if __name__ == "__main__":
    import sys
    target_pom = sys.argv[1] if len(sys.argv) > 1 else "pom.xml"
    inject_jacoco_into_pom(target_pom)